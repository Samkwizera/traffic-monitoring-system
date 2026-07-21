"""
Smart Traffic-Density Monitoring System — Streamlit dashboard.

Run from the repo root with:

    streamlit run app/dashboard.py

Features
--------
1. Upload a traffic image or video.
2. See detected vehicles with bounding boxes.
3. See total vehicle count + traffic-density level (Low/Moderate/High).
4. Record each reading with location, date and time.
5. Compare traffic across the monitored roads.
6. Get a recommendation for the least-congested / alternative route.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import streamlit as st

# Allow `streamlit run app/dashboard.py` from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config                                   # noqa: E402
from app.density import density_color                    # noqa: E402
from app.logger import log_detection, load_log, latest_per_location  # noqa: E402
from app.routing import rank_roads, recommend_route      # noqa: E402


# --------------------------------------------------------------------------
# Page setup
# --------------------------------------------------------------------------
st.set_page_config(
    page_title="Rwanda Smart Traffic Monitor",
    page_icon="🚦",
    layout="wide",
)


@st.cache_resource(show_spinner="Loading YOLO model (first run downloads weights)...")
def _load_detector():
    """Load the detector once and reuse it across reruns/sessions."""
    from app.detector import VehicleDetector
    return VehicleDetector()


def _density_badge(level: str) -> str:
    color = density_color(level)
    return (
        f"<span style='background:{color};color:white;padding:4px 12px;"
        f"border-radius:12px;font-weight:600'>{level}</span>"
    )


# --------------------------------------------------------------------------
# Sidebar controls
# --------------------------------------------------------------------------
st.sidebar.title("🚦 Traffic Monitor")
st.sidebar.caption("Smart Traffic-Density Monitoring System — Rwanda (prototype)")

location = st.sidebar.selectbox(
    "Road / camera location", list(config.LOCATIONS.keys())
)

st.sidebar.subheader("Density thresholds (vehicles)")
low_max = st.sidebar.slider(
    "Low  ≤", 1, 50, config.DENSITY_THRESHOLDS["low_max"]
)
moderate_max = st.sidebar.slider(
    "Moderate ≤", low_max + 1, 100,
    max(config.DENSITY_THRESHOLDS["moderate_max"], low_max + 1),
)
# Apply live threshold edits to the shared config.
config.DENSITY_THRESHOLDS["low_max"] = low_max
config.DENSITY_THRESHOLDS["moderate_max"] = moderate_max

confidence = st.sidebar.slider("Detection confidence", 0.1, 0.9, config.CONFIDENCE_THRESHOLD, 0.05)

st.sidebar.info(
    "Thresholds should be **calibrated per camera** — the count depends on how "
    "much road each camera sees."
)


# --------------------------------------------------------------------------
# Main tabs
# --------------------------------------------------------------------------
st.title("Smart Traffic-Density Monitoring System")
st.caption("Detect & count vehicles, classify congestion, and find the clearest route.")

tab_detect, tab_compare, tab_route = st.tabs(
    ["🔍 Detect", "📊 Compare roads", "🧭 Route recommendation"]
)


# ---- Tab 1: detection -----------------------------------------------------
with tab_detect:
    st.subheader(f"Analyse traffic — {location}")
    upload = st.file_uploader(
        "Upload a traffic image or video",
        type=["jpg", "jpeg", "png", "bmp", "mp4", "avi", "mov", "mkv"],
    )

    if upload is not None:
        detector = _load_detector()
        detector.confidence = confidence
        suffix = Path(upload.name).suffix.lower()
        is_video = suffix in {".mp4", ".avi", ".mov", ".mkv"}

        with st.spinner("Detecting vehicles..."):
            if is_video:
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(upload.read())
                    tmp_path = tmp.name
                result = detector.detect_video(tmp_path)
            else:
                file_bytes = np.frombuffer(upload.read(), dtype=np.uint8)
                image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
                result = detector.detect_image(image)

        # Metrics row
        c1, c2, c3 = st.columns(3)
        c1.metric("Total vehicles", result.vehicle_count)
        c2.markdown("**Traffic density**")
        c2.markdown(_density_badge(result.density), unsafe_allow_html=True)
        c3.metric("Frames analysed", result.frames_processed)

        # Annotated output with bounding boxes (convert BGR -> RGB for display)
        if result.annotated_image is not None:
            rgb = cv2.cvtColor(result.annotated_image, cv2.COLOR_BGR2RGB)
            st.image(rgb, caption="Detected vehicles", use_container_width=True)

        # Per-class breakdown
        if result.counts_by_class:
            breakdown = pd.DataFrame(
                sorted(result.counts_by_class.items(), key=lambda x: -x[1]),
                columns=["vehicle type", "count"],
            )
            st.bar_chart(breakdown.set_index("vehicle type"))

        # Save this reading to the log
        if st.button("💾 Save this reading to the log", type="primary"):
            record = log_detection(
                result, location=location,
                source="video" if is_video else "image",
            )
            st.success(
                f"Saved: {record['date']} {record['time']} · {record['location']} · "
                f"{record['vehicle_count']} vehicles · {record['density']}"
            )
    else:
        st.info("👆 Upload a traffic image or short video to begin.")


# ---- Tab 2: compare roads -------------------------------------------------
with tab_compare:
    st.subheader("Compare traffic across monitored roads")
    latest = latest_per_location()

    if latest.empty:
        st.info(
            "No readings logged yet. Analyse traffic on the **Detect** tab and "
            "save readings to populate this comparison."
        )
    else:
        ranked = rank_roads(latest)
        display = ranked[["rank", "location", "vehicle_count", "density", "time", "date"]]
        st.dataframe(display, use_container_width=True, hide_index=True)

        chart_df = ranked.set_index("location")["vehicle_count"]
        st.bar_chart(chart_df)

        clearest = ranked.iloc[0]
        busiest = ranked.iloc[-1]
        c1, c2 = st.columns(2)
        c1.success(f"🟢 Clearest: **{clearest['location']}** ({clearest['density']})")
        c2.error(f"🔴 Busiest: **{busiest['location']}** ({busiest['density']})")

    with st.expander("View full detection log"):
        st.dataframe(load_log(), use_container_width=True, hide_index=True)


# ---- Tab 3: route recommendation -----------------------------------------
with tab_route:
    st.subheader("Least-congested route recommendation")
    destination = st.selectbox(
        "Where are you heading?", list(config.LOCATIONS.keys()), key="dest"
    )
    latest = latest_per_location()
    rec = recommend_route(destination, latest)

    st.markdown(f"### {rec['message']}")

    if rec["alternatives"]:
        alt_df = pd.DataFrame(rec["alternatives"])
        alt_df.columns = ["road", "current density"]
        st.markdown("**Options ranked from clearest to busiest:**")
        st.dataframe(alt_df, use_container_width=True, hide_index=True)

        best = rec["recommended"]
        st.markdown(
            f"➡️ **Recommended:** {best} — "
            + _density_badge(rec["recommended_density"]),
            unsafe_allow_html=True,
        )

    st.caption(
        "Alternatives come from the road graph in `app/config.py` "
        "(`LOCATIONS[...].connects_to`). Replace with a real routing engine "
        "(OSRM / Google Directions) for production."
    )


st.divider()
st.caption(
    "Prototype · YOLOv8 + OpenCV + Streamlit · Detection records include vehicle "
    "count, density, location, date & time. See README for the IoT camera roadmap."
)
