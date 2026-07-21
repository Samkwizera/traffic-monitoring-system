"""
Detection-record logging.

Every detection produces a record with the fields the brief asks for:
vehicle count, traffic-density level, location, date and time. Records are
appended to a CSV so the dashboard can compare roads over time and the data
could later feed a database / IoT backend.
"""

from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pandas as pd

from . import config

if TYPE_CHECKING:  # avoid importing detector (and cv2/torch) at runtime
    from .detector import DetectionResult

FIELDNAMES = [
    "timestamp",
    "date",
    "time",
    "location",
    "vehicle_count",
    "density",
    "cars",
    "motorcycles",
    "buses",
    "trucks",
    "bicycles",
    "source",
]


def log_detection(
    result: "DetectionResult",
    location: str,
    source: str = "upload",
    csv_path: Path | None = None,
) -> dict:
    """Append one detection record to the CSV log and return it as a dict."""
    csv_path = csv_path or config.LOG_CSV
    now = datetime.now()
    c = result.counts_by_class
    record = {
        "timestamp": now.isoformat(timespec="seconds"),
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "location": location,
        "vehicle_count": result.vehicle_count,
        "density": result.density,
        "cars": c.get("car", 0),
        "motorcycles": c.get("motorcycle", 0),
        "buses": c.get("bus", 0),
        "trucks": c.get("truck", 0),
        "bicycles": c.get("bicycle", 0),
        "source": source,
    }

    csv_path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(record)

    return record


def load_log(csv_path: Path | None = None) -> pd.DataFrame:
    """Load all detection records as a DataFrame (empty if none yet)."""
    csv_path = csv_path or config.LOG_CSV
    if not Path(csv_path).exists():
        return pd.DataFrame(columns=FIELDNAMES)
    return pd.read_csv(csv_path)


def latest_per_location(csv_path: Path | None = None) -> pd.DataFrame:
    """Return the most recent record for each monitored location."""
    df = load_log(csv_path)
    if df.empty:
        return df
    df = df.sort_values("timestamp")
    return df.groupby("location", as_index=False).last()
