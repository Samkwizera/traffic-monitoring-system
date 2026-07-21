"""
Road comparison and route recommendation.

Given the latest density reading for each monitored road, this module:

  * ranks roads from least to most congested, and
  * recommends the least-congested alternative to a chosen destination road
    using the lightweight road graph defined in ``config.LOCATIONS``.

The recommendation is intentionally simple (greedy over current density) —
enough for a prototype and easy to replace with a real routing engine
(e.g. OSRM / Google Directions) later.
"""

from __future__ import annotations

import pandas as pd

from . import config
from .density import density_score


def rank_roads(latest_df: pd.DataFrame) -> pd.DataFrame:
    """Rank roads from least to most congested.

    ``latest_df`` is expected to have ``location``, ``density`` and
    ``vehicle_count`` columns (see ``logger.latest_per_location``).
    """
    if latest_df.empty:
        return latest_df

    df = latest_df.copy()
    df["density_score"] = df["density"].map(density_score)
    # Lower score = clearer road. Break ties with the raw vehicle count.
    df = df.sort_values(["density_score", "vehicle_count"], ascending=True)
    df = df.reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df


def recommend_route(destination: str, latest_df: pd.DataFrame) -> dict:
    """Recommend the least-congested way to reach ``destination``.

    Returns a dict describing the destination's own status, the best
    alternative connected road, and a human-readable message.
    """
    result: dict = {
        "destination": destination,
        "destination_density": "Unknown",
        "recommended": destination,
        "recommended_density": "Unknown",
        "alternatives": [],
        "message": "",
    }

    if latest_df.empty:
        result["message"] = (
            "No traffic data yet. Analyse a few roads first to enable "
            "route recommendations."
        )
        return result

    by_loc = latest_df.set_index("location")

    def status_of(road: str) -> str:
        if road in by_loc.index:
            return str(by_loc.loc[road, "density"])
        return "Unknown"

    dest_density = status_of(destination)
    result["destination_density"] = dest_density

    # Candidate roads: the destination plus its neighbours in the road graph.
    neighbours = config.LOCATIONS.get(destination, {}).get("connects_to", [])
    candidates = [destination] + [n for n in neighbours if n in by_loc.index]

    ranked = sorted(candidates, key=lambda r: density_score(status_of(r)))
    best = ranked[0]

    result["recommended"] = best
    result["recommended_density"] = status_of(best)
    result["alternatives"] = [
        {"road": r, "density": status_of(r)} for r in ranked
    ]

    if best == destination:
        result["message"] = (
            f"'{destination}' is currently {dest_density.lower()} — go ahead, "
            f"it is the clearest option."
        )
    else:
        result["message"] = (
            f"'{destination}' is {dest_density.lower()} traffic. Consider "
            f"'{best}' instead — it is currently "
            f"{status_of(best).lower()}."
        )
    return result
