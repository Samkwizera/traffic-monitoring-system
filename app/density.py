"""
Traffic-density classification.

Turns a raw vehicle count into a human-readable density level
(Low / Moderate / High) using the thresholds in ``config.py``.
"""

from __future__ import annotations

from . import config


def classify_density(vehicle_count: int, thresholds: dict | None = None) -> str:
    """Classify traffic density from a vehicle count.

    Parameters
    ----------
    vehicle_count:
        Number of vehicles detected in the frame/image.
    thresholds:
        Optional override of ``{"low_max": int, "moderate_max": int}``.
        Falls back to ``config.DENSITY_THRESHOLDS``.

    Returns
    -------
    str
        One of ``"Low"``, ``"Moderate"`` or ``"High"``.
    """
    t = thresholds or config.DENSITY_THRESHOLDS
    if vehicle_count <= t["low_max"]:
        return "Low"
    if vehicle_count <= t["moderate_max"]:
        return "Moderate"
    return "High"


def density_score(level: str) -> int:
    """Numeric weight for a density level (used for ranking roads)."""
    return config.DENSITY_WEIGHT.get(level, config.DENSITY_WEIGHT["Unknown"])


def density_color(level: str) -> str:
    """Hex colour associated with a density level (for the dashboard)."""
    return config.DENSITY_COLORS.get(level, config.DENSITY_COLORS["Unknown"])
