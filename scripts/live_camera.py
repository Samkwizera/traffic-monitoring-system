"""
Live edge-camera loop — Arduino + Arducam OV2640 -> YOLO -> LED traffic light.

Each cycle:
    1. ask the Arduino to capture a frame (over USB serial),
    2. run YOLO on the laptop to count vehicles + classify density,
    3. log the record (count, density, location, date, time),
    4. tell the Arduino which colour to show on its LED,
    5. (optionally) display the annotated frame and/or publish over MQTT,
    then wait `--interval` seconds and repeat.

Find your board's port first:
    python -c "from app.camera_serial import list_ports; print(list_ports())"

Run:
    python scripts/live_camera.py --port COM5 --location "KN 1 Rd - City Centre" --show
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config                       # noqa: E402
from app.camera_serial import ArduCamSerial, MockArduCam, list_ports  # noqa: E402
from app.detector import get_detector        # noqa: E402
from app.logger import log_detection         # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Live Arduino/Arducam traffic monitor")
    parser.add_argument("--port", help="Serial port (e.g. COM5 or /dev/ttyACM0)")
    parser.add_argument("--location", default=config.DEFAULT_LOCATION)
    parser.add_argument("--interval", type=float, default=3.0,
                        help="Seconds between captures")
    parser.add_argument("--frames", type=int, default=0,
                        help="Stop after N frames (0 = run until Ctrl+C)")
    parser.add_argument("--show", action="store_true",
                        help="Show the annotated frame in an OpenCV window")
    parser.add_argument("--no-log", action="store_true", help="Do not write CSV logs")
    parser.add_argument("--mqtt", action="store_true", help="Also publish over MQTT")
    parser.add_argument("--mock", action="store_true",
                        help="No hardware: cycle through data/samples/ images")
    parser.add_argument("--samples", default=None,
                        help="Folder of images for --mock (default: data/samples/)")
    parser.add_argument("--list-ports", action="store_true",
                        help="List serial ports and exit")
    args = parser.parse_args()

    if args.list_ports:
        print("Available serial ports:", list_ports() or "(none found)")
        return 0
    if not args.mock and not args.port:
        print("ERROR: --port is required (or use --mock). See --list-ports.",
              file=sys.stderr)
        return 2

    detector = get_detector()

    mqtt_pub = None
    if args.mqtt:
        from app.iot_publisher import TrafficMQTTPublisher
        mqtt_pub = TrafficMQTTPublisher()

    if args.mock:
        print("MOCK mode: cycling sample images (no hardware).")
        cam = MockArduCam(args.samples)
    else:
        print(f"Connecting to {args.port} ...")
        cam = ArduCamSerial(args.port)
    print("Starting capture loop (Ctrl+C to stop).\n")

    n = 0
    try:
        while args.frames == 0 or n < args.frames:
            n += 1
            try:
                frame = cam.capture()
            except Exception as exc:  # noqa: BLE001 - keep the loop alive
                print(f"[{n}] capture failed: {exc}")
                time.sleep(args.interval)
                continue

            result = detector.detect_image(frame)
            cam.set_led(result.density)          # drive the traffic light

            stamp = time.strftime("%H:%M:%S")
            print(f"[{n}] {stamp}  {result.summary()}  @ {args.location}")

            if not args.no_log:
                log_detection(result, location=args.location, source="arducam")
            if mqtt_pub is not None:
                try:
                    mqtt_pub.publish_result(result, location=args.location)
                except Exception as exc:  # noqa: BLE001
                    print(f"    MQTT publish failed: {exc}")

            if args.show and result.annotated_image is not None:
                cv2.imshow("Live traffic (press q to quit)", result.annotated_image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        cam.close()
        if mqtt_pub is not None:
            mqtt_pub.disconnect()
        if args.show:
            cv2.destroyAllWindows()

    print(f"Done. Processed {n} frame(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
