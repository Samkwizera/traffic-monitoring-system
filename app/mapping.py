"""
Map rendering for the dashboard (pydeck).

Builds an interactive map of the monitored roads:
  * each road is a marker coloured by its current density (green/amber/red),
  * the road-graph connections are drawn as thin grey lines, and
  * the recommended alternative route is highlighted as a thick line.

pydeck ships with Streamlit and uses a Carto basemap by default, so no
Mapbox API key is required.
"""

from __future__ import annotations

import pandas as pd
import pydeck as pdk

from . import config

_HIGHLIGHT_RGB = [30, 136, 229]   # blue — the recommended route


def _nodes_frame(latest_df: pd.DataFrame) -> pd.DataFrame:
    """One row per monitored road: coords, current density, count, colour."""
    by_loc = {}
    if latest_df is not None and not latest_df.empty:
        by_loc = latest_df.set_index("location").to_dict("index")

    rows = []
    for name, meta in config.LOCATIONS.items():
        coords = meta.get("coords")
        if not coords:
            continue
        lat, lon = coords
        rec = by_loc.get(name, {})
        density = str(rec.get("density", "Unknown"))
        count = int(rec.get("vehicle_count", 0) or 0)
        rows.append({
            "location": name,
            "lat": lat,
            "lon": lon,
            "density": density,
            "count": count,
            "color": config.density_rgb(density),
            # marker radius grows a little with congestion (metres)
            "radius": 120 + count * 8,
        })
    return pd.DataFrame(rows)


def _edges_frame() -> pd.DataFrame:
    """Undirected road-graph edges as from/to coordinate pairs."""
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
            rows.append({
                "from_lon": a[1], "from_lat": a[0],
                "to_lon": b[1], "to_lat": b[0],
            })
    return pd.DataFrame(rows)


def build_map(latest_df: pd.DataFrame, rec: dict | None = None) -> pdk.Deck:
    """Build the pydeck map. ``rec`` is the dict from ``routing.recommend_route``.

    If ``rec`` describes a detour (recommended != destination), that edge is
    drawn highlighted on top of the road graph.
    """
    nodes = _nodes_frame(latest_df)
    edges = _edges_frame()

    layers = [
        # Road-graph connections (thin grey).
        pdk.Layer(
            "LineLayer",
            data=edges,
            get_source_position="[from_lon, from_lat]",
            get_target_position="[to_lon, to_lat]",
            get_color=[150, 150, 150],
            get_width=2,
        ),
        # Road markers coloured by density.
        pdk.Layer(
            "ScatterplotLayer",
            data=nodes,
            get_position="[lon, lat]",
            get_fill_color="color",
            get_radius="radius",
            radius_min_pixels=6,
            radius_max_pixels=40,
            pickable=True,
            opacity=0.8,
            stroked=True,
            get_line_color=[255, 255, 255],
            line_width_min_pixels=1,
        ),
        # Road name labels.
        pdk.Layer(
            "TextLayer",
            data=nodes,
            get_position="[lon, lat]",
            get_text="location",
            get_size=12,
            get_color=[20, 20, 20],
            get_alignment_baseline="'top'",
            get_pixel_offset=[0, 12],
        ),
    ]

    # Highlight the recommended detour, if any.
    if rec and rec.get("recommended") and rec.get("destination") \
            and rec["recommended"] != rec["destination"]:
        a = config.LOCATIONS.get(rec["destination"], {}).get("coords")
        b = config.LOCATIONS.get(rec["recommended"], {}).get("coords")
        if a and b:
            hl = pd.DataFrame([{
                "from_lon": a[1], "from_lat": a[0],
                "to_lon": b[1], "to_lat": b[0],
            }])
            layers.append(pdk.Layer(
                "LineLayer",
                data=hl,
                get_source_position="[from_lon, from_lat]",
                get_target_position="[to_lon, to_lat]",
                get_color=_HIGHLIGHT_RGB,
                get_width=6,
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
        map_style=None,   # default Carto basemap (no API key needed)
        tooltip={"html": "<b>{location}</b><br/>{count} vehicles &mdash; {density}"},
    )
