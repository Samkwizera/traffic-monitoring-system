"""
Download a few sample traffic images for testing the detector.

    python scripts/download_samples.py

Images are pulled from stable public URLs (Ultralytics + Wikimedia Commons,
all freely usable) into ``data/samples/``. If a URL is unavailable the script
skips it and continues.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402

# Wikimedia's Special:FilePath is a stable redirect to the current file,
# so it does not break when thumbnail paths change.
_COMMONS = "https://commons.wikimedia.org/wiki/Special:FilePath/"

# (filename, url) — reliable, freely-usable images that contain vehicles.
SAMPLES = [
    # Ultralytics demo image: a red double-decker bus + people.
    ("bus.jpg", "https://ultralytics.com/images/bus.jpg"),
    # Wikimedia Commons: dense multi-vehicle traffic jams.
    ("traffic_jam.jpg", _COMMONS + "Traffic_jam.jpg"),
    ("bangkok_traffic.jpg", _COMMONS + "Bangkok_traffic_by_g-hat.jpg"),
]

# A browser-like UA avoids some 403s from Wikimedia.
HEADERS = {"User-Agent": "Mozilla/5.0 (traffic-monitor-prototype)"}


def download(name: str, url: str, dest_dir: Path) -> bool:
    dest = dest_dir / name
    if dest.exists():
        print(f"  [OK]   {name} already present, skipping")
        return True
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as fh:
            fh.write(resp.read())
        print(f"  [OK]   downloaded {name}  ({dest.stat().st_size // 1024} KB)")
        return True
    except Exception as exc:  # noqa: BLE001 - best-effort downloader
        print(f"  [FAIL] could not download {name}: {exc}")
        if dest.exists():
            dest.unlink()
        return False


def main() -> int:
    print(f"Downloading sample images into {config.SAMPLES_DIR} ...")
    ok = sum(download(n, u, config.SAMPLES_DIR) for n, u in SAMPLES)
    print(f"\nDone: {ok}/{len(SAMPLES)} images available.")
    if ok == 0:
        print("No downloads succeeded (offline?). Drop your own images into "
              f"{config.SAMPLES_DIR} instead.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
