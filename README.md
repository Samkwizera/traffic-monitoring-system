# 🚦 Smart Traffic-Density Monitoring System — Rwanda

A functional prototype that detects and counts vehicles from a traffic **image
or video**, classifies traffic density as **Low / Moderate / High**, records the
result (vehicle count, density, **location, date and time**), compares congestion
across roads, and recommends the **least-congested / alternative route**.

Built with **Python + OpenCV + YOLOv8 (Ultralytics)** and a **Streamlit** dashboard.

---

## Table of contents
1. [How it works](#how-it-works)
2. [Folder structure](#folder-structure)
3. [Installation](#installation)
4. [Running the prototype](#running-the-prototype)
5. [Tuning & configuration](#tuning--configuration)
6. [Development roadmap (MVP → IoT)](#development-roadmap-mvp--iot)
7. [Connecting to real IoT cameras](#connecting-to-real-iot-cameras)
8. [Troubleshooting](#troubleshooting)

---

## How it works

```
 Image / Video ──► YOLOv8 detection ──► keep vehicle classes ──► count
                        (OpenCV)          (car, moto, bus,          │
                                           truck, bicycle)          ▼
                                                          Density classifier
                                                       (Low / Moderate / High)
                                                                    │
                        ┌───────────────────────────────────────────┤
                        ▼                                            ▼
                 Log record (CSV)                          Annotated image
        count · density · location · date · time          (bounding boxes)
                        │
                        ▼
        Compare roads  +  Recommend least-congested route
                        (Streamlit dashboard)
```

Vehicle classes counted (COCO IDs): **car (2), motorcycle (3), bus (5),
truck (7), bicycle (1)** — motorcycles ("motos") are included because they
dominate Rwandan urban traffic.

---

## Folder structure

```
traffic-monitoring-system/
├── app/                     # application package
│   ├── __init__.py
│   ├── config.py            # model, thresholds, vehicle classes, road graph
│   ├── detector.py          # YOLO + OpenCV vehicle detection (image & video)
│   ├── density.py           # count → Low/Moderate/High classification
│   ├── logger.py            # append detection records to CSV
│   ├── routing.py           # rank roads + recommend least-congested route
│   ├── iot_publisher.py     # MQTT publisher stub (IoT integration step)
│   └── dashboard.py         # Streamlit dashboard (main UI)
├── scripts/
│   ├── detect_cli.py        # MVP step 1 — command-line detector
│   ├── download_samples.py  # fetch sample traffic images into data/samples/
│   └── seed_demo_data.py    # seed demo readings for Compare/Route tabs
├── data/
│   ├── samples/             # put your test images / videos here
│   └── results/             # detections_log.csv + annotated outputs
├── models/                  # YOLO weights (auto-downloaded on first run)
├── requirements.txt
├── .gitignore
└── README.md
```

---

## Installation

> ✅ **Python 3.11–3.14 all work.** This prototype was verified on **Python
> 3.14** (torch 2.13 ships `cp314` wheels). Always install inside a virtual
> environment so system packages stay clean.

### 1. Check your Python
```bash
python --version   # 3.11, 3.12, 3.13 or 3.14 are all fine
```

### 2. Create and activate a virtual environment

**Windows (PowerShell):**
```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```
The first detection run downloads the YOLOv8-nano weights (`yolov8n.pt`, ~6 MB)
automatically into `models/` (or the ultralytics cache).

---

## Running the prototype

### A. Command-line MVP (fastest way to verify it works)
```bash
# (optional) grab a few sample traffic images first
python scripts/download_samples.py

# Image
python scripts/detect_cli.py --image data/samples/traffic_jam.jpg --location "KN 1 Rd - City Centre"

# Video
python scripts/detect_cli.py --video data/samples/traffic.mp4 --location "RN1 - Nyanza Rd"

# Also publish the record to an MQTT broker (see IoT section)
python scripts/detect_cli.py --image data/samples/traffic_jam.jpg --mqtt
```
Prints the vehicle count + density, saves an annotated image to `data/results/`,
and appends a record to `data/results/detections_log.csv`.

### B. Streamlit dashboard (full experience)
```bash
# (optional) seed some demo readings so Compare/Route tabs have data
python scripts/seed_demo_data.py

streamlit run app/dashboard.py
```
Then open the URL Streamlit prints (usually http://localhost:8501).

**Dashboard tabs**
- **🔍 Detect** — upload an image/video, view bounding boxes, total count,
  density level and per-class breakdown; save the reading with location + timestamp.
- **📊 Compare roads** — table + chart ranking every monitored road from clearest
  to busiest, with the current clearest/busiest highlighted.
- **🧭 Route recommendation** — pick a destination road; get the least-congested
  connected alternative.

---

## Tuning & configuration

All tunables live in [`app/config.py`](app/config.py):

| Setting | What it controls |
|---|---|
| `MODEL_NAME` | `yolov8n.pt` (fast) → `yolov8s/m.pt` (more accurate) |
| `CONFIDENCE_THRESHOLD` | Minimum detection confidence |
| `VEHICLE_CLASSES` | Which COCO classes count as vehicles |
| `DENSITY_THRESHOLDS` | `low_max` / `moderate_max` count cut-offs |
| `LOCATIONS` | Monitored roads + `connects_to` road graph for routing |

> **Calibrate density thresholds per camera.** The vehicle count depends on how
> much road a camera sees, so a "High" on one camera is not the same as on
> another. The dashboard sidebar lets you adjust thresholds live while testing.

---

## Development roadmap (MVP → IoT)

The project is built in incremental, working slices:

- **Step 1 — CLI MVP ✅**  `scripts/detect_cli.py`: image/video → count → density → log.
- **Step 2 — Detection engine ✅**  `app/detector.py`: reusable YOLO wrapper, image & video, bounding boxes.
- **Step 3 — Records & density ✅**  `app/density.py` + `app/logger.py`: Low/Moderate/High + CSV logging with location/date/time.
- **Step 4 — Dashboard ✅**  `app/dashboard.py`: upload, visualise, save readings.
- **Step 5 — Compare & route ✅**  `app/routing.py`: rank roads, recommend alternatives.
- **Step 6 — IoT integration (next)**  live camera streams, a database, and a map. See below.

---

## Connecting to real IoT cameras

The prototype is deliberately structured so the detection core stays the same
when you move from uploaded files to live cameras.

**1. Swap the input source.** `VehicleDetector._detect_frame()` already works on
any BGR frame. For a live IP/RTSP camera:
```python
cap = cv2.VideoCapture("rtsp://user:pass@camera-ip:554/stream")
while True:
    ok, frame = cap.read()
    if not ok:
        break
    counts, annotated, _ = detector._detect_frame(frame)
    # classify + publish (see below)
```

**2. Edge vs. cloud.**
- *Edge* — run YOLO on a device at the roadside (e.g. **NVIDIA Jetson Nano/Orin**
  or **Raspberry Pi 5 + Coral/Hailo accelerator**). Only small JSON results
  (count, density, location, timestamp) are sent upstream — cheap on bandwidth.
- *Cloud* — cameras stream RTSP to a server that runs detection centrally.
  Simpler devices, higher bandwidth/compute cost.

**3. Publish results, don't just log to CSV.** A working MQTT publisher stub
already ships in [`app/iot_publisher.py`](app/iot_publisher.py). It turns each
detection into JSON and publishes it to a per-camera topic:

```python
from app.iot_publisher import TrafficMQTTPublisher

pub = TrafficMQTTPublisher(host="broker-ip", port=1883)
pub.publish_result(result, location="KN 1 Rd - City Centre")
# -> topic  traffic/kigali/kn-1-rd-city-centre
#    payload {"location": ..., "vehicle_count": 32, "density": "High", ...}
```

Try it locally with Mosquitto:
```bash
mosquitto -v                       # 1. start a broker
mosquitto_sub -t 'traffic/#' -v    # 2. subscribe in another terminal
python -m app.iot_publisher --demo # 3. publish a demo record
# or attach it to a real detection:
python scripts/detect_cli.py --image data/samples/traffic_jam.jpg --mqtt
```

Alternatively **REST/DB**: `POST` each record to an API backed by
PostgreSQL/TimescaleDB or Firebase for time-series history.

**4. Real-time dashboard.** Point the dashboard at the live database instead of
the CSV (`logger.load_log`/`latest_per_location` are the only two functions to
change). Add auto-refresh (`st_autorefresh`) and a map (`st.map` / Folium) with
each camera's GPS coordinates coloured by density.

**5. Real routing.** Swap the `connects_to` graph in `config.LOCATIONS` for a
real routing engine (**OSRM**, **OpenStreetMap**, or **Google Directions API**),
feeding live per-segment density as edge weights so the recommender returns true
turn-by-turn alternatives.

**Suggested production architecture:**
```
[IoT cameras] --RTSP--> [Edge device: YOLO] --MQTT--> [Broker]
                                                          │
                                                          ▼
                                            [Backend + Time-series DB]
                                                          │
                                        ┌─────────────────┴───────────────┐
                                        ▼                                 ▼
                             [Streamlit / web dashboard]        [Routing engine + alerts]
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `pip install` builds numpy from source / is very slow | Ensure `numpy>=1.26` (unpinned upper bound) so pip uses a prebuilt wheel for your Python. |
| `ImportError: ultralytics is not installed` | Run `pip install -r requirements.txt` inside the activated venv. |
| First run is slow | It is downloading YOLO weights (one-time). |
| Detection misses vehicles | Lower `CONFIDENCE_THRESHOLD` or use a bigger model (`yolov8s/m.pt`). |
| Density label looks wrong | Calibrate `DENSITY_THRESHOLDS` for that camera's field of view. |
| Video processing is slow | It samples frames (`sample_every`, `max_frames` in `detect_video`); increase the stride. |

---

*Prototype for educational / research use. Detection accuracy depends on camera
angle, lighting, weather and model size — validate before any operational use.*
