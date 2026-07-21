"""
Vehicle detection with YOLO + OpenCV.

This module wraps the Ultralytics YOLO model and exposes two high-level
functions the rest of the app uses:

    detect_image(image)  -> DetectionResult
    detect_video(path)   -> DetectionResult   (aggregated over sampled frames)

The heavy ``ultralytics`` import is done lazily inside ``VehicleDetector`` so
that importing this module (e.g. for tests or the density logic) does not
require torch to be installed.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import config
from .density import classify_density


# --------------------------------------------------------------------------
# Result container
# --------------------------------------------------------------------------
@dataclass
class DetectionResult:
    """Outcome of running detection on one image or a whole video."""

    vehicle_count: int
    density: str
    counts_by_class: dict = field(default_factory=dict)
    annotated_image: np.ndarray | None = None      # BGR frame with boxes drawn
    frames_processed: int = 1
    inference_ms: float = 0.0

    def summary(self) -> str:
        by_class = ", ".join(f"{k}: {v}" for k, v in self.counts_by_class.items())
        return (
            f"{self.vehicle_count} vehicles ({by_class}) -> {self.density} density"
        )


# --------------------------------------------------------------------------
# Detector
# --------------------------------------------------------------------------
class VehicleDetector:
    """Loads a YOLO model once and reuses it for image/video inference."""

    def __init__(
        self,
        model_name: str = config.MODEL_NAME,
        confidence: float = config.CONFIDENCE_THRESHOLD,
    ):
        self.model_name = model_name
        self.confidence = confidence
        self._model = None  # lazy-loaded

    # -- model loading ------------------------------------------------------
    @property
    def model(self):
        """Lazily construct the YOLO model (downloads weights on first use)."""
        if self._model is None:
            try:
                from ultralytics import YOLO
            except ImportError as exc:  # pragma: no cover - env dependent
                raise ImportError(
                    "ultralytics is not installed. Run "
                    "`pip install -r requirements.txt` in a Python 3.11/3.12 "
                    "environment (torch has no wheels for 3.13/3.14 yet)."
                ) from exc

            # Prefer a local copy in models/, else let ultralytics fetch it.
            weights = config.MODEL_PATH if config.MODEL_PATH.exists() else self.model_name
            self._model = YOLO(str(weights))
        return self._model

    # -- core frame inference ----------------------------------------------
    def _detect_frame(self, frame: np.ndarray, draw: bool = True):
        """Run YOLO on a single BGR frame.

        Returns ``(counts_by_class, annotated_frame, inference_ms)``.
        """
        start = time.perf_counter()
        results = self.model.predict(
            frame,
            conf=self.confidence,
            classes=list(config.VEHICLE_CLASSES.keys()),
            verbose=False,
        )
        inference_ms = (time.perf_counter() - start) * 1000.0

        counts: dict[str, int] = {}
        annotated = frame.copy() if draw else None
        result = results[0]

        for box in result.boxes:
            cls_id = int(box.cls[0])
            label = config.VEHICLE_CLASSES.get(cls_id)
            if label is None:
                continue
            counts[label] = counts.get(label, 0) + 1

            if draw:
                conf = float(box.conf[0])
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0])
                color = config.CLASS_COLORS.get(label, config.DEFAULT_COLOR)
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                tag = f"{label} {conf:.2f}"
                (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
                cv2.rectangle(annotated, (x1, y1 - th - 6), (x1 + tw, y1), color, -1)
                cv2.putText(
                    annotated, tag, (x1, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
                )

        return counts, annotated, inference_ms

    # -- public: image ------------------------------------------------------
    def detect_image(self, image: np.ndarray) -> DetectionResult:
        """Detect vehicles in a single BGR image (numpy array)."""
        counts, annotated, ms = self._detect_frame(image, draw=True)
        total = sum(counts.values())
        annotated = _overlay_banner(annotated, total, classify_density(total))
        return DetectionResult(
            vehicle_count=total,
            density=classify_density(total),
            counts_by_class=counts,
            annotated_image=annotated,
            frames_processed=1,
            inference_ms=ms,
        )

    # -- public: video ------------------------------------------------------
    def detect_video(
        self,
        video_path: str | Path,
        sample_every: int = 15,
        max_frames: int = 60,
    ) -> DetectionResult:
        """Detect vehicles across a video by sampling frames.

        We sample one frame every ``sample_every`` frames (up to
        ``max_frames`` samples) and report the **peak** vehicle count seen,
        which is what determines whether a road is congested. The annotated
        image returned is the busiest sampled frame.
        """
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError(f"Could not open video: {video_path}")

        frame_idx = 0
        samples = 0
        total_ms = 0.0
        peak_count = 0
        peak_counts: dict[str, int] = {}
        peak_frame: np.ndarray | None = None

        try:
            while samples < max_frames:
                ret, frame = cap.read()
                if not ret:
                    break
                if frame_idx % sample_every == 0:
                    counts, annotated, ms = self._detect_frame(frame, draw=True)
                    total = sum(counts.values())
                    total_ms += ms
                    samples += 1
                    if total >= peak_count:
                        peak_count = total
                        peak_counts = counts
                        peak_frame = annotated
                frame_idx += 1
        finally:
            cap.release()

        density = classify_density(peak_count)
        if peak_frame is not None:
            peak_frame = _overlay_banner(peak_frame, peak_count, density)

        return DetectionResult(
            vehicle_count=peak_count,
            density=density,
            counts_by_class=peak_counts,
            annotated_image=peak_frame,
            frames_processed=samples,
            inference_ms=total_ms,
        )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _overlay_banner(image: np.ndarray | None, count: int, density: str):
    """Draw a summary banner (count + density) on the top-left of the image."""
    if image is None:
        return None
    color = {
        "Low": (0, 150, 0),
        "Moderate": (0, 170, 240),
        "High": (0, 0, 220),
    }.get(density, (80, 80, 80))
    text = f"Vehicles: {count}  |  Density: {density}"
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.7, 2)
    cv2.rectangle(image, (0, 0), (tw + 20, th + 20), color, -1)
    cv2.putText(
        image, text, (10, th + 10),
        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
    )
    return image


# --------------------------------------------------------------------------
# Module-level convenience (shared singleton so the model loads only once)
# --------------------------------------------------------------------------
_default_detector: VehicleDetector | None = None


def get_detector() -> VehicleDetector:
    """Return a process-wide shared detector (loads the model on first call)."""
    global _default_detector
    if _default_detector is None:
        _default_detector = VehicleDetector()
    return _default_detector


def detect_image(image: np.ndarray) -> DetectionResult:
    return get_detector().detect_image(image)


def detect_video(video_path: str | Path, **kwargs) -> DetectionResult:
    return get_detector().detect_video(video_path, **kwargs)
