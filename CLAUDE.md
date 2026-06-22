# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository. Deep architecture reference is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Overview

Safespace Node is an edge-based road safety monitoring system running on a **Raspberry Pi** with a Sony IMX500 AI camera. It captures video, runs accident-detection models, streams an RTSP feed via MediaMTX, and communicates with a Central Unit server via Socket.IO and raw WebSockets.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3 |
| GUI | PyQt6 (from `apt`) |
| Computer vision | OpenCV (`cv2`), `supervision` |
| AI inference | Ultralytics YOLO (`.pt`), ONNX Runtime (`.onnx`) |
| Camera | `picamera2` + Sony IMX500 NPU |
| RTSP streaming | MediaMTX (server) + `ffmpeg` subprocess (publisher) |
| Networking | `python-socketio`, `websocket-client`, `requests` |
| Config | PyYAML — single `configs/config.yaml` |
| Logging | Python `logging` + `RotatingFileHandler` → `logs/safespace.log` |
| GPS | `pyserial` → SIM808 UART |
| System metrics | `psutil` |

---

## Project Structure

```
Safespace_node/
├── configs/
│   ├── config.yaml          single config file — all settings
│   └── mediamtx.yml         MediaMTX config — RTSP on :8554, single "live" path
├── docs/
│   └── ARCHITECTURE.md      threading diagrams, data flow, gotchas
├── models/
│   ├── *.pt                 YOLO weights (gitignored / large)
│   ├── *.onnx               ONNX weights
│   └── *.rpk                IMX500 compiled network
├── assets/
│   ├── road_signs_icons/    SVGs used by LaneWidget
│   └── accidents_images/    fallback accident image
├── logs/                    rotating log output (created at runtime, project root)
├── src/
│   ├── main.py              SafespaceNode orchestrator + CLI entry point
│   ├── managers/
│   │   ├── ai.py            AIManager — inference loop + model registry
│   │   ├── input.py         InputManager — capture loop
│   │   ├── output.py        OutputManager — display bridge
│   │   ├── network.py       NetworkManager — heartbeat + accident + commands
│   │   └── stream.py        StreamManager — MediaMTX subprocess + StreamHandler
│   ├── handlers/
│   │   ├── camera.py        CameraHandler (picam / imx500 / imx500-raw)
│   │   ├── stream_handler.py StreamHandler — FrameBuffer → ffmpeg → MediaMTX RTSP
│   │   ├── video.py         VideoHandler (file playback, same interface as camera)
│   │   ├── frame_buffer.py  FrameBuffer — deque + threading.Lock
│   │   ├── model_loader.py  ModelLoader — auto-detect .pt/.onnx, LRU cache
│   │   ├── model_detection.py ModelDetection — YOLO track(), ONNX letterbox+NMS
│   │   ├── onnx_model.py    OnnxModel — onnxruntime session wrapper
│   │   ├── socket.py        SocketHandler — Socket.IO + raw WS
│   │   ├── gps_handler.py   GPSHandler — SIM808 UART polling
│   │   └── display/
│   │       ├── display_handler.py  public API (wraps QApplication + MainWindow)
│   │       ├── main_window.py      dev/prod layouts + pyqtSignals
│   │       ├── lane_widget.py      lane icon + status label
│   │       ├── speed_widget.py     speed limit display
│   │       ├── video_feed_widget.py  BGR→RGB QPixmap in QLabel
│   │       └── system_monitor_widget.py  psutil CPU/RAM bars
│   ├── utils/
│   │   ├── config.py        Config — YAML load + dot-notation get/set + env overrides
│   │   ├── logger.py        Logger — RotatingFileHandler + stdout; call Logger.setup() once
│   │   ├── constants.py     global constants (API paths, event names, status strings)
│   │   └── failures.py      SafespaceError hierarchy + FailureManager (threshold tracker)
│   └── test_display.py      manual GUI test — no camera/network needed
├── requirements.txt         Pi pip deps (PyQt6 + picamera2 come from apt)
└── .env.example             ROBOFLOW_API_KEY
```

**Convention for new files:** handlers go in `src/handlers/`, managers in `src/managers/`, utilities in `src/utils/`. New display widgets go in `src/handlers/display/`. Constants go in `src/utils/constants.py`. Never import across the package from outside `src/` — the entry point sets `sys.path`.

---

## Commands

### Install (Raspberry Pi)

```bash
# System packages — PyQt6 and picamera2 must come from apt, not pip
sudo apt update && sudo apt install -y python3-pyqt6 python3-picamera2 ffmpeg

# Create venv with system packages so apt-installed libs are visible
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
```

### Run

```bash
# PYTHONPATH must point to project root so src/ imports resolve
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 src/main.py

# With a video file instead of camera (dev/test)
python3 src/main.py --video path/to/video.mp4

# Flags (combinable)
python3 src/main.py --no-ai           # skip model inference
python3 src/main.py --no-display      # headless mode
python3 src/main.py --no-network      # offline mode
python3 src/main.py --no-stream       # disable RTSP streaming
```

**GUI control:** Spacebar triggers a manual accident report; Escape closes the window.

### RTSP streaming setup

```bash
# 1. Install ffmpeg (done in system packages step above)
# 2. Download MediaMTX binary (ARM64 for Pi 4/5):
#    https://github.com/bluenviron/mediamtx/releases
#    Set stream.mediamtx_path in config.yaml to the full binary path.
# 3. In configs/config.yaml set:
#    camera.model: "imx500-raw"
#    stream.enabled: true
# Central Unit then pulls:  rtsp://<node-ip>:8554/live
```

### Manual display test (no camera or network)

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 src/test_display.py
```

---

## Configuration

All settings live in `configs/config.yaml`. Access via dot-notation:

```python
config.get('camera.fps')                      # → 30
config.get_int('node.lanes', 4)
config.get_float('camera.imx500.confidence', 0.5)
config.get_bool('display.fullscreen', False)
```

### Environment overrides

| Env var | Config key |
|---|---|
| `NODE_ID` | `node.id` |
| `SERVER_URL` | `network.server_url` |
| `LOG_LEVEL` | `logging.level` |

### Key config keys

| Key | Purpose |
|---|---|
| `node.id` | Unique identifier sent in every network payload |
| `node.lanes` | Number of lane widgets in the GUI |
| `node.default_speed` | Speed shown on startup / after reset |
| `node.location.lat/long` | Static GPS fallback when SIM808 has no fix |
| `camera.model` | `"imx500-raw"` (default) / `"imx500"` (on-chip NPU) / `"picam"` |
| `camera.imx500.camera_num` | Picamera2 camera index for IMX500 hardware (default 0) |
| `stream.enabled` | Enable RTSP streaming via MediaMTX + ffmpeg |
| `stream.port` | MediaMTX RTSP port (default 8554) |
| `stream.path` | Stream path — Central Unit pulls `rtsp://<node-ip>:<port>/<path>` |
| `stream.fps` | Push rate to MediaMTX (independent of `camera.fps`) |
| `stream.mediamtx_path` | Full path to the MediaMTX binary |
| `ai.models.<name>` | `path`, `type`, `confidence`, `enabled`, `target_classes` |
| `network.server_url` | Central Unit base URL (`http://` or `https://`) |
| `network.ws_path` | Raw WS endpoint appended to server URL |
| `network.accident_cooldown` | Seconds between duplicate accident reports |
| `gps.port` | UART device, e.g. `/dev/ttyAMA0` |
| `display.mode` | `"dev"` (video feeds + metrics) or `"prod"` (lanes + speed only) |
| `logging.file_logging` | Logs written to `logs/safespace.log` at project root |

---

## Conventions & Gotchas

### Imports and PYTHONPATH

All `src/` modules import each other with bare names (`from utils.config import Config`). This requires `PYTHONPATH` to include the project root **and** `sys.path` to include `src/`. `main.py` adds its own directory (`src/`) to `sys.path` when run as `__main__`. Always run from the project root with `PYTHONPATH=$PYTHONPATH:$(pwd)`.

### Qt thread safety — never skip the signal

All Qt widget mutations must happen on the **main thread** via `pyqtSignal`. Call the public methods (`update_lane()`, `update_speed()`, etc.) from any thread — they emit the signal. **Never call `_update_lane()` / `_update_speed()` / etc. directly from a background thread.**

### Logging pattern

Call `Logger.setup(config.get('logging', {}))` exactly once (done in `SafespaceNode.__init__`). Then create a per-class instance: `self.logger = Logger("ClassName")`. Logs land at `logs/safespace.log` in the project root.

### Model path resolution

`AIManager._load_model()` resolves model paths relative to the project root. Paths in `ai.models.<name>.path` should be relative to the project root (e.g., `models/best_MSamir.pt`).

### Adding a new model

1. Add the model file to `models/`.
2. Add an entry under `ai.models` in `configs/config.yaml` with `type`, `path`, `confidence`, `enabled`, `target_classes`.
3. `AIManager` auto-loads all `enabled: true` models at startup; `.pt` → YOLO, `.onnx` → OnnxModel.

### Adding a new WS command

Extend `NetworkManager._on_command()` with a new `elif command_id == "..."` branch. Add the constant to `src/utils/constants.py`.

### IMX500 camera modes

| `camera.model` | On-chip NPU | Software AI | RTSP stream |
|---|---|---|---|
| `imx500` | ✓ loads `.rpk` | ✗ disabled | optional |
| `imx500-raw` | ✗ no model loaded | ✓ enabled | ✓ primary use case |
| `picam` | ✗ | ✓ | optional |

`camera.model: "imx500"` sets `enable_ai = False` before `AIManager` is constructed. `imx500-raw` does not — software AI runs normally.

### Accident payload format

Single detection → `accidentPolygon.points` is a flat list of 4 `{x, y}` dicts. Multiple detections → list of lists.

### picamera2 / NumPy ABI mismatch

If `picamera2` crashes with `numpy.dtype size changed`, the environment has NumPy 2.x. Pin `numpy<2` (already in `requirements.txt`). Install `python3-picamera2` from `apt` before creating the venv.

### ONNX model class names

`OnnxModel._extract_names()` parses class names from ONNX custom metadata. If names were not embedded at export, it falls back to `class_<id>` labels — `target_classes` filtering will silently fail to match.

For threading diagrams, data flow details, and known risks see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
