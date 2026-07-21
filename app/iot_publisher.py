"""
IoT integration stub — publish detection records to an MQTT broker.

This is the bridge between the detection core and a real-time IoT backend.
Instead of (or in addition to) writing a CSV, each detection record is
published as JSON to a per-camera MQTT topic, e.g.:

    traffic/kigali/kn-1-city-centre  ->  {"location": ..., "vehicle_count": 32,
                                          "density": "High", "timestamp": ...}

A backend service (or another dashboard) subscribes to ``traffic/#`` and
stores / visualises the stream. ``paho-mqtt`` is imported lazily so the rest
of the app does not depend on it.

Quick local test
----------------
1. Run a broker (e.g. Mosquitto):  ``mosquitto -v``
2. Subscribe in one terminal:      ``mosquitto_sub -t 'traffic/#' -v``
3. Publish a demo record:          ``python -m app.iot_publisher --demo``
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from . import config


def topic_for(location: str, prefix: str = "traffic/kigali") -> str:
    """Build a clean MQTT topic from a location label.

    'KN 1 Rd - City Centre' -> 'traffic/kigali/kn-1-rd-city-centre'
    """
    slug = re.sub(r"[^a-z0-9]+", "-", location.lower()).strip("-")
    return f"{prefix}/{slug}"


def build_payload(
    location: str,
    vehicle_count: int,
    density: str,
    counts_by_class: dict | None = None,
    camera_id: str | None = None,
) -> dict[str, Any]:
    """Assemble the JSON payload for one detection record."""
    now = datetime.now()
    return {
        "camera_id": camera_id or topic_for(location).split("/")[-1],
        "location": location,
        "vehicle_count": vehicle_count,
        "density": density,
        "counts_by_class": counts_by_class or {},
        "timestamp": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
    }


class TrafficMQTTPublisher:
    """Thin wrapper around paho-mqtt for publishing detection records."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1883,
        topic_prefix: str = "traffic/kigali",
        username: str | None = None,
        password: str | None = None,
        client_id: str = "traffic-monitor-edge",
    ):
        self.host = host
        self.port = port
        self.topic_prefix = topic_prefix
        self._client = None
        self._creds = (username, password)
        self._client_id = client_id

    def connect(self) -> None:
        try:
            import paho.mqtt.client as mqtt
        except ImportError as exc:  # pragma: no cover - optional dep
            raise ImportError(
                "paho-mqtt is not installed. Run `pip install paho-mqtt` "
                "to use the MQTT publisher."
            ) from exc

        # paho-mqtt 2.x requires the callback API version.
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=self._client_id
        )
        user, pwd = self._creds
        if user:
            self._client.username_pw_set(user, pwd)
        self._client.connect(self.host, self.port, keepalive=60)
        self._client.loop_start()

    def publish(
        self,
        location: str,
        vehicle_count: int,
        density: str,
        counts_by_class: dict | None = None,
        qos: int = 1,
    ) -> dict:
        """Publish one detection record; returns the payload that was sent."""
        if self._client is None:
            self.connect()
        payload = build_payload(location, vehicle_count, density, counts_by_class)
        topic = topic_for(location, self.topic_prefix)
        self._client.publish(topic, json.dumps(payload), qos=qos, retain=True)
        return {"topic": topic, **payload}

    def publish_result(self, result, location: str, qos: int = 1) -> dict:
        """Convenience: publish straight from a ``DetectionResult``."""
        return self.publish(
            location=location,
            vehicle_count=result.vehicle_count,
            density=result.density,
            counts_by_class=result.counts_by_class,
            qos=qos,
        )

    def disconnect(self) -> None:
        if self._client is not None:
            self._client.loop_stop()
            self._client.disconnect()
            self._client = None


# --------------------------------------------------------------------------
# Demo / CLI: publish a fake record so you can watch it arrive on the broker.
# --------------------------------------------------------------------------
def _demo() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="MQTT publisher demo")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--location", default=config.DEFAULT_LOCATION)
    parser.add_argument("--count", type=int, default=32)
    parser.add_argument("--density", default="High")
    parser.add_argument("--demo", action="store_true", help="run the demo publish")
    args = parser.parse_args()

    pub = TrafficMQTTPublisher(host=args.host, port=args.port)
    try:
        sent = pub.publish(args.location, args.count, args.density,
                           counts_by_class={"car": 20, "motorcycle": 10, "bus": 2})
        print("Published to topic:", sent["topic"])
        print(json.dumps({k: v for k, v in sent.items() if k != "topic"}, indent=2))
    except Exception as exc:  # noqa: BLE001
        print(f"Could not publish: {exc}")
        print("Is an MQTT broker running on "
              f"{args.host}:{args.port}? (e.g. `mosquitto -v`)")
        return 1
    finally:
        pub.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(_demo())
