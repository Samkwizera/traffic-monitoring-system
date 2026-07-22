"""
Map rendering for the dashboard (pydeck) — Google-Maps-style traffic overlay.

Instead of point markers, each monitored road is drawn as a thick line that
follows the real street geometry and is coloured by its current density:

    green = Low   ·   orange = Moderate   ·   red = High

Road geometry is fetched once from the public OSRM routing service (no API key)
so the coloured lines snap to actual roads and line up with the basemap, then
cached to disk. If OSRM is unreachable, we fall back to straight lines.
"""

from __future__ import annotations

import json
import urllib.request

import pandas as pd
import pydeck as pdk

from . import config
from .density import density_score

# Bright Google-traffic-like colours for the road overlay.
ROAD_COLORS = {
    "Low": [67, 160, 71],       # green
    "Moderate": [251, 140, 0],  # orange
    "High": [183, 28, 28],      # dark red
    "Unknown": [160, 160, 160], # grey (no data yet)
}
_DETOUR_RGB = [30, 136, 229]    # blue — the recommended detour

# OSRM geometry cache (endpoints -> list of [lon, lat]).
_CACHE_FILE = config.RESULTS_DIR / "road_geometry_cache.json"
_OSRM_URL = (
    "https://router.project-osrm.org/route/v1/driving/"
    "{lon1},{lat1};{lon2},{lat2}?overview=full&geometries=geojson"
)


def _load_cache() -> dict:
    if _CACHE_FILE.exists():
        try:
            return json.loads(_CACHE_FILE.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_FILE.write_text(json.dumps(cache))
    except Exception:
        pass


_geom_cache = _load_cache()


def _road_geometry(a: tuple, b: tuple) -> list[list[float]]:
    """Return the driving-road polyline [[lon, lat], ...] between two points.

    Uses OSRM (cached); falls back to a straight segment when offline.
    ``a`` and ``b`` are (lat, lon) tuples.
    """
    key = f"{a[0]:.5f},{a[1]:.5f};{b[0]:.5f},{b[1]:.5f}"
    if key in _geom_cache:
        return _geom_cache[key]

    straight = [[a[1], a[0]], [b[1], b[0]]]
    try:
        url = _OSRM_URL.format(lon1=a[1], lat1=a[0], lon2=b[1], lat2=b[0])
        with urllib.request.urlopen(url, timeout=8) as resp:
            data = json.load(resp)
        coords = data["routes"][0]["geometry"]["coordinates"]  # [[lon,lat],...]
        if coords:
            _geom_cache[key] = coords
            _save_cache(_geom_cache)
            return coords
    except Exception:
        pass
    return straight


def _worse_density(d1: str, d2: str) -> str:
    """Return the more-congested of two density levels (colours the segment)."""
    return d1 if density_score(d1) >= density_score(d2) else d2


def _density_by_location(latest_df: pd.DataFrame) -> dict:
    if latest_df is None or latest_df.empty:
        return {}
    return {
        row["location"]: str(row["density"])
        for _, row in latest_df.iterrows()
    }


def _nodes_frame(latest_df: pd.DataFrame) -> pd.DataFrame:
    """Small camera markers with density/count for tooltips."""
    dens = _density_by_location(latest_df)
    counts = {}
    if latest_df is not None and not latest_df.empty:
        counts = {r["location"]: int(r["vehicle_count"] or 0)
                  for _, r in latest_df.iterrows()}
    rows = []
    for name, meta in config.LOCATIONS.items():
        coords = meta.get("coords")
        if not coords:
            continue
        density = dens.get(name, "Unknown")
        rows.append({
            "location": name,
            "lat": coords[0],
            "lon": coords[1],
            "density": density,
            "count": counts.get(name, 0),
            "color": ROAD_COLORS.get(density, ROAD_COLORS["Unknown"]),
        })
    return pd.DataFrame(rows)


def _edges_frame(latest_df: pd.DataFrame) -> pd.DataFrame:
    """One coloured, road-following path per road-graph connection."""
    dens = _density_by_location(latest_df)
    seen = set()
    rows = []
    for name, meta in config.LOCATIONS.items():
        a = meta.get("coords")
        if not a:
            continue
        for other in meta.get("connects_to", []):
            b = config.LOCATIONS.get(other, {}).get("coords")
            if not b:
                continue
            key = tuple(sorted([name, other]))
            if key in seen:
                continue
            seen.add(key)
            density = _worse_density(dens.get(name, "Unknown"),
                                     dens.get(other, "Unknown"))
            rows.append({
                "path": _road_geometry(a, b),
                "color": ROAD_COLORS.get(density, ROAD_COLORS["Unknown"]),
                "density": density,
                "segment": f"{name}  ↔  {other}",
            })
    return pd.DataFrame(rows)


def build_map(latest_df: pd.DataFrame, rec: dict | None = None) -> pdk.Deck:
    """Build the pydeck traffic-overlay map.

    ``rec`` is the dict from ``routing.recommend_route``; when it describes a
    detour, that route is highlighted in blue on top of the coloured roads.
    """
    nodes = _nodes_frame(latest_df)
    edges = _edges_frame(latest_df)

    layers = [
        # Coloured road segments (the traffic overlay).
        pdk.Layer(
            "PathLayer",
            data=edges,
            get_path="path",
            get_color="color",
            get_width=6,
            width_min_pixels=5,
            width_max_pixels=9,
            cap_rounded=True,
            joint_rounded=True,
            pickable=True,
        ),
        # Small camera markers.
        pdk.Layer(
            "ScatterplotLayer",
            data=nodes,
            get_position="[lon, lat]",
            get_fill_color=[255, 255, 255],
            get_line_color=[60, 60, 60],
            get_radius=60,
            radius_min_pixels=3,
            radius_max_pixels=6,
            stroked=True,
            line_width_min_pixels=1,
            pickable=True,
        ),
    ]

    # Highlight the recommended detour route (blue), drawn on top.
    if rec and rec.get("recommended") and rec.get("destination") \
            and rec["recommended"] != rec["destination"]:
        a = config.LOCATIONS.get(rec["destination"], {}).get("coords")
        b = config.LOCATIONS.get(rec["recommended"], {}).get("coords")
        if a and b:
            hl = pd.DataFrame([{"path": _road_geometry(a, b)}])
            layers.append(pdk.Layer(
                "PathLayer",
                data=hl,
                get_path="path",
                get_color=_DETOUR_RGB,
                get_width=10,
                width_min_pixels=8,
                width_max_pixels=12,
                cap_rounded=True,
                joint_rounded=True,
                opacity=0.6,
            ))

    view_state = pdk.ViewState(
        latitude=config.MAP_CENTER[0],
        longitude=config.MAP_CENTER[1],
        zoom=config.MAP_ZOOM,
        pitch=0,
    )
    return pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_provider="carto",
        map_style="road",   # light street basemap (Google-Maps-like)
        tooltip={"html": "<b>{segment}</b><br/>Traffic: {density}"},
    )
