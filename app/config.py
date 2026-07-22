"""
Central configuration for the Smart Traffic-Density Monitoring System.

Everything that a deployment might need to tune lives here so the rest of
the code stays clean: which object classes count as "vehicles", the density
thresholds, the model to use, and the list of monitored road locations in
Rwanda.
"""

from __future__ import annotations

from pathlib import Path

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
MODELS_DIR = BASE_DIR / "models"
DATA_DIR = BASE_DIR / "data"
SAMPLES_DIR = DATA_DIR / "samples"
RESULTS_DIR = DATA_DIR / "results"

# Where per-detection records are appended (vehicle count, density, location, time)
LOG_CSV = RESULTS_DIR / "detections_log.csv"

# Make sure runtime directories exist.
for _d in (MODELS_DIR, DATA_DIR, SAMPLES_DIR, RESULTS_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# Model
# --------------------------------------------------------------------------
# YOLOv8-nano: small and fast, good for a prototype / CPU laptops.
# Ultralytics downloads the weights automatically on first use.
# Swap to "yolov8s.pt" / "yolov8m.pt" for higher accuracy at more compute.
MODEL_NAME = "yolov8n.pt"
MODEL_PATH = MODELS_DIR / MODEL_NAME

# Minimum confidence for a detection to be counted.
CONFIDENCE_THRESHOLD = 0.35

# --------------------------------------------------------------------------
# Vehicle classes
# --------------------------------------------------------------------------
# COCO class IDs that we treat as vehicles. Motorcycles matter a lot in
# Rwanda ("motos"), so they are included alongside cars, buses and trucks.
#   1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck
VEHICLE_CLASSES = {
    2: "car",
    3: "motorcycle",
    5: "bus",
    7: "truck",
    1: "bicycle",
}

# Colours (BGR, for OpenCV) used to draw boxes per class.
CLASS_COLORS = {
    "car": (0, 200, 0),
    "motorcycle": (0, 165, 255),
    "bus": (255, 0, 0),
    "truck": (0, 0, 255),
    "bicycle": (200, 0, 200),
}
DEFAULT_COLOR = (0, 255, 255)

# --------------------------------------------------------------------------
# Traffic-density classification
# --------------------------------------------------------------------------
# Thresholds are on the vehicle count within a single frame/image.
# These are prototype defaults — they should be *calibrated per camera*
# because the count depends on how much road each camera sees.
#   count <= LOW_MAX               -> "Low"
#   LOW_MAX < count <= MODERATE_MAX-> "Moderate"
#   count  > MODERATE_MAX          -> "High"
DENSITY_THRESHOLDS = {
    "low_max": 10,
    "moderate_max": 25,
}

DENSITY_LEVELS = ("Low", "Moderate", "High")

# Colours for density badges in the dashboard (hex).
DENSITY_COLORS = {
    "Low": "#2e7d32",       # green
    "Moderate": "#f9a825",  # amber
    "High": "#c62828",      # red
    "Unknown": "#616161",
}

# --------------------------------------------------------------------------
# Monitored locations (example Kigali / Rwanda roads)
# --------------------------------------------------------------------------
# In a real deployment each entry maps to a physical IoT camera. The
# `connects_to` field is a lightweight road graph used by the route
# recommender to suggest alternatives, and `coords` (lat, lon) places the
# camera on the map. Coordinates below are APPROXIMATE Kigali placeholders —
# replace them with each camera's real GPS position on deployment.
LOCATIONS = {
    "KN 1 Rd - City Centre": {
        "connects_to": ["RN1 - Nyanza Rd", "KG 11 Ave - Kimironko"],
        "coords": (-1.9499, 30.0589),
    },
    "RN1 - Nyanza Rd": {
        "connects_to": ["KN 1 Rd - City Centre", "KK 15 Rd - Kicukiro"],
        "coords": (-1.9820, 30.0730),
    },
    "KG 11 Ave - Kimironko": {
        "connects_to": ["KN 1 Rd - City Centre", "KK 15 Rd - Kicukiro"],
        "coords": (-1.9540, 30.1140),
    },
    "KK 15 Rd - Kicukiro": {
        "connects_to": ["RN1 - Nyanza Rd", "KG 11 Ave - Kimironko"],
        "coords": (-1.9840, 30.1030),
    },
    "RN3 - Rusizi Highway": {
        "connects_to": ["KK 15 Rd - Kicukiro"],
        "coords": (-2.0100, 30.0400),
    },
}

# Map centre + zoom for the dashboard (roughly Kigali).
MAP_CENTER = (-1.9700, 30.0750)
MAP_ZOOM = 11


def density_rgb(level: str) -> list[int]:
    """Return an [R, G, B] colour for a density level (for map layers)."""
    hex_color = DENSITY_COLORS.get(level, DENSITY_COLORS["Unknown"]).lstrip("#")
    return [int(hex_color[i:i + 2], 16) for i in (0, 2, 4)]

DEFAULT_LOCATION = "KN 1 Rd - City Centre"

# Numeric weight per density level, used to rank roads for routing.
DENSITY_WEIGHT = {"Low": 1, "Moderate": 2, "High": 3, "Unknown": 2}
