"""
MVP Step 1 — command-line vehicle detector.

The simplest end-to-end slice of the system: point it at an image or video,
it detects and counts vehicles, classifies traffic density, logs the record
(count, density, location, date, time) and saves an annotated output image.

Usage
-----
    python scripts/detect_cli.py --image data/samples/road.jpg --location "KN 1 Rd - City Centre"
    python scripts/detect_cli.py --video data/samples/traffic.mp4 --location "RN1 - Nyanza Rd"

Run with no model present and Ultralytics will auto-download YOLOv8n.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2

# Allow running as `python scripts/detect_cli.py` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config                       # noqa: E402
from app.detector import get_detector        # noqa: E402
from app.logger import log_detection         # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Smart Traffic-Density detector (CLI MVP)")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--image", type=str, help="Path to a traffic image")
    src.add_argument("--video", type=str, help="Path to a traffic video")
    parser.add_argument(
        "--location", type=str, default=config.DEFAULT_LOCATION,
        help="Road/camera location label to record",
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Where to save the annotated output (defaults to data/results/)",
    )
    parser.add_argument(
        "--mqtt", action="store_true",
        help="Also publish the record to an MQTT broker (IoT step)",
    )
    parser.add_argument("--mqtt-host", default="localhost")
    parser.add_argument("--mqtt-port", type=int, default=1883)
    args = parser.parse_args()

    detector = get_detector()

    if args.image:
        image = cv2.imread(args.image)
        if image is None:
            print(f"ERROR: could not read image '{args.image}'", file=sys.stderr)
            return 1
        print("Running detection on image...")
        result = detector.detect_image(image)
        source = "image"
    else:
        print("Running detection on video (sampling frames)...")
        result = detector.detect_video(args.video)
        source = "video"

    # Report
    print("\n=== Detection result ===")
    print(result.summary())
    print(f"Location:        {args.location}")
    print(f"Frames analysed: {result.frames_processed}")
    print(f"Inference time:  {result.inference_ms:.0f} ms")

    # Log record (count, density, location, date, time)
    record = log_detection(result, location=args.location, source=source)
    print(f"\nLogged to: {config.LOG_CSV}")
    print(f"  {record['date']} {record['time']} | {record['location']} | "
          f"{record['vehicle_count']} vehicles | {record['density']}")

    # Optionally publish to MQTT (IoT integration step)
    if args.mqtt:
        from app.iot_publisher import TrafficMQTTPublisher
        pub = TrafficMQTTPublisher(host=args.mqtt_host, port=args.mqtt_port)
        try:
            sent = pub.publish_result(result, location=args.location)
            print(f"Published to MQTT topic: {sent['topic']}")
        except Exception as exc:  # noqa: BLE001
            print(f"MQTT publish failed: {exc}", file=sys.stderr)
        finally:
            pub.disconnect()

    # Save annotated output
    if result.annotated_image is not None:
        out_path = Path(args.out) if args.out else (
            config.RESULTS_DIR / f"annotated_{record['timestamp'].replace(':', '-')}.jpg"
        )
        cv2.imwrite(str(out_path), result.annotated_image)
        print(f"Annotated image saved to: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
