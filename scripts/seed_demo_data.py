"""
Seed the detection log with sample readings so the 'Compare roads' and
'Route recommendation' tabs are demonstrable without running the model.

    python scripts/seed_demo_data.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import csv                       # noqa: E402
from app import config           # noqa: E402
from app.density import classify_density  # noqa: E402
from app.logger import FIELDNAMES         # noqa: E402

# (location, vehicle_count) demo snapshots
DEMO = [
    ("KN 1 Rd - City Centre", 32),
    ("RN1 - Nyanza Rd", 8),
    ("KG 11 Ave - Kimironko", 18),
    ("KK 15 Rd - Kicukiro", 27),
    ("RN3 - Rusizi Highway", 5),
]


def main() -> int:
    now = datetime.now()
    config.LOG_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(config.LOG_CSV, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        writer.writeheader()
        for i, (loc, count) in enumerate(DEMO):
            ts = now - timedelta(minutes=len(DEMO) - i)
            density = classify_density(count)
            writer.writerow({
                "timestamp": ts.isoformat(timespec="seconds"),
                "date": ts.strftime("%Y-%m-%d"),
                "time": ts.strftime("%H:%M:%S"),
                "location": loc,
                "vehicle_count": count,
                "density": density,
                "cars": int(count * 0.6),
                "motorcycles": int(count * 0.3),
                "buses": max(0, int(count * 0.05)),
                "trucks": max(0, int(count * 0.05)),
                "bicycles": 0,
                "source": "seed",
            })
    print(f"Seeded {len(DEMO)} demo readings into {config.LOG_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
