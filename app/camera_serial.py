"""
Laptop-side client for the Arduino + Arducam OV2640 edge node.

Speaks the simple serial protocol implemented in
``arduino/arducam_traffic/arducam_traffic.ino``:

    -> b'c'   request a frame     <- 0xA5 0x5A <len u32 LE> <jpeg bytes>
    -> b'0'/b'1'/b'2'/b'x'        set the on-board LED (green/amber/red/off)

The returned frame is decoded straight into a BGR numpy array, ready to feed
into ``VehicleDetector.detect_image``.
"""

from __future__ import annotations

import struct
import time

import cv2
import numpy as np

MAGIC = b"\xA5\x5A"
# Density level -> LED command byte understood by the sketch.
LED_FOR_DENSITY = {"Low": b"0", "Moderate": b"1", "High": b"2"}


class ArduCamSerial:
    """Capture JPEG frames from the Arduino/Arducam node over USB serial."""

    def __init__(self, port: str, baud: int = 115200, timeout: float = 5.0,
                 warmup: float = 2.0):
        try:
            import serial  # pyserial
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ImportError(
                "pyserial is not installed. Run `pip install pyserial` "
                "(it is in requirements.txt)."
            ) from exc

        self._serial = serial
        self.ser = serial.Serial(port, baud, timeout=timeout)
        # Opening the port resets the board; wait for it to boot.
        time.sleep(warmup)
        self.ser.reset_input_buffer()

    # -- LED control --------------------------------------------------------
    def set_led(self, density: str) -> None:
        """Set the traffic-light LED from a density level."""
        self.ser.write(LED_FOR_DENSITY.get(density, b"x"))

    def led_off(self) -> None:
        self.ser.write(b"x")

    # -- frame capture ------------------------------------------------------
    def _read_exact(self, n: int) -> bytes:
        """Read exactly ``n`` bytes or raise on timeout."""
        buf = bytearray()
        while len(buf) < n:
            chunk = self.ser.read(n - len(buf))
            if not chunk:
                raise TimeoutError(
                    f"Serial timeout: got {len(buf)}/{n} bytes. "
                    "Is the sketch flashed and the port correct?"
                )
            buf.extend(chunk)
        return bytes(buf)

    def _sync_to_magic(self, max_scan: int = 4_000_000) -> None:
        """Advance the stream until the 2-byte magic marker is found."""
        window = b""
        scanned = 0
        while scanned < max_scan:
            b = self.ser.read(1)
            if not b:
                raise TimeoutError("Timed out waiting for frame magic marker.")
            window = (window + b)[-2:]
            scanned += 1
            if window == MAGIC:
                return
        raise ValueError("Never saw the frame magic marker.")

    def capture(self) -> np.ndarray:
        """Request one frame and return it as a decoded BGR image."""
        self.ser.reset_input_buffer()
        self.ser.write(b"c")

        self._sync_to_magic()
        (length,) = struct.unpack("<I", self._read_exact(4))
        if length == 0 or length > 512 * 1024:
            raise ValueError(f"Implausible frame length: {length} bytes")

        jpeg = self._read_exact(length)
        image = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError("Failed to decode JPEG frame (corrupt transfer).")
        return image

    def close(self) -> None:
        try:
            self.led_off()
        finally:
            self.ser.close()

    # Context-manager sugar.
    def __enter__(self) -> "ArduCamSerial":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def list_ports() -> list[str]:
    """Return available serial port names (helper for the CLI)."""
    try:
        from serial.tools import list_ports as _lp
    except ImportError:
        return []
    return [p.device for p in _lp.comports()]
