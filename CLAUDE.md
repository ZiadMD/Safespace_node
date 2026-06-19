# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Overview

Safespace Node is an edge-based road safety monitoring system that runs on a Raspberry Pi (or laptop for dev). It captures video from a camera (or the Sony IMX500 AI camera), runs accident-detection models, streams a PyQt6 dashboard, and communicates with a Central Unit server via Socket.IO and raw WebSockets.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3 |
| GUI | PyQt6 |
| Computer vision | OpenCV (`cv2`), `supervision` |
| AI inference | Ultralytics YOLO (`.pt`), ONNX Runtime (`.onnx`) |
| Camera (Pi) | `picamera2` + Sony IMX500 NPU |
| RTSP streaming | MediaMTX (server) + `ffmpeg` subprocess (publisher) |
| Networking | `python-socketio`, `websocket-client`, `requests` |
| Config | PyYAML — single `configs/config.yaml` |
| Logging | Python `logging` + `RotatingFileHandler` |
| GPS | `pyserial` → SIM808 UART |
| System metrics | `psutil` |

---

## Architecture

### Layer diagram

```
SafespaceNode  (src/main.py)
├── GPSHandler           SIM808 UART → live lat/long
├── FrameBuffer          thread-safe deque ring buffer (shared)
├── InputManager
│   ├── CameraHandler    native (OpenCV) / picam / imx500 / imx500-raw
│   └── VideoHandler     video file (dev/test mode)
├── AIManager
│   ├── ModelLoader      auto-detects .pt → YOLO, .onnx → OnnxModel
│   └── ModelDetection   inference + NMS + class filtering → sv.Detections
├── StreamManager                           ← RTSP streaming
│   ├── MediaMTX subprocess                 serves rtsp://<node-ip>:8554/live
│   └── StreamHandler                       FrameBuffer → ffmpeg → MediaMTX
├── OutputManager
│   └── DisplayHandler → MainWindow (PyQt6)
│       ├── VideoFeedWidget   (dev mode: input feed + AI feed)
│       ├── LaneWidget        (N lanes, icon + status label)
│       ├── SpeedWidget       (speed limit, alert mode)
│       └── SystemMonitorWidget (CPU/RAM bars, dev mode only)
└── NetworkManager
    └── SocketHandler
        ├── Socket.IO   → emit accident report, receive ACK
        └── Raw WS      → receive commands (accident-decision)
```

### Threading model

| Thread name | Owner | What it does |
|---|---|---|
| **MainThread** | Qt event loop | All GUI rendering. Other threads push data via `pyqtSignal`. |
| **InputCapture** | `InputManager` | Reads frames at target FPS → `FrameBuffer`, fires `on_frame` callback. |
| **AIInference** | `AIManager` | Pulls latest frame from `FrameBuffer`, runs all enabled models. Runs free-running (no sleep); naturally drops frames when GPU/CPU is slow. |
| **Heartbeat** | `NetworkManager` | HTTP POST `/api/nodes/heartbeat` every N seconds. Uses a `time.sleep(0.1)` poll loop internally. |
| **SIOConnect** | `SocketHandler` | Connects the `python-socketio` client in a background thread. |
| **WSCommandListener** | `SocketHandler` | `websocket-client` event loop; receives server commands; auto-reconnects with exponential backoff (max 30 s). |
| **AccidentReport** *(transient)* | `NetworkManager` | Spawned per confirmed detection after cooldown. Encodes frame → base64 JPEG and emits `node_accident_detected` via Socket.IO. |
| **RTSPStream** | `StreamHandler` | Pulls frames from `FrameBuffer` at `stream.fps`, pipes raw BGR bytes to ffmpeg stdin; ffmpeg publishes H.264 to MediaMTX. Restarts ffmpeg on crash with exponential backoff (2 s → 30 s). |

### Core data flow

```
Camera/Video → InputCapture thread
    ├─ write_frame() → FrameBuffer (deque, lock-protected)
    └─ on_frame callback → push_input_frame_signal → VideoFeedWidget (dev mode)

FrameBuffer → AIInference thread
    ├─ get_latest_with_timestamp()
    ├─ ModelDetection.detect() → sv.Detections
    ├─ on_frame_processed callback → push_ai_frame_signal → VideoFeedWidget (dev mode)
    └─ on_detection callback (if len > 0)
           ├─ OutputManager.on_accident_detected() → set_accident_signal → banner + SpeedWidget
           └─ NetworkManager.report_accident()
                  └─ AccidentReport thread → SocketHandler.emit_accident()
                         └─ Socket.IO → Central Unit → ACK → incidentId stored

Central Unit → WSCommandListener thread (raw WebSocket)
    └─ _on_command() → _handle_accident_decision()
           ├─ CONFIRMED → on_road_update(lanes, speed_limit) → lane/speed signals
           └─ REJECTED  → on_accident_cleared() → reset_display_signal
```

### IMX500 camera modes

| `camera.model` | On-chip NPU | Software AI | RTSP stream |
|---|---|---|---|
| `imx500` | ✓ loads `.rpk` | ✗ disabled | optional |
| `imx500-raw` | ✗ no model loaded | ✓ enabled | ✓ primary use case |
| `picam` | ✗ | ✓ | optional |
| `native` | ✗ | ✓ | optional |

**`imx500` path (on-chip inference):** `SafespaceNode.__init__` sets `enable_ai = False` unconditionally. Detections come from the NPU:

```
IMX500 picamera2 → _read_frame_imx500() → frame + np_outputs (boxes/scores/classes)
    ↓ get_imx500_detections()
InputManager._capture_loop → on_imx500_detection callback
    ↓ SafespaceNode._on_imx500_detection()
        → confidence filter → sv.Detections → annotate frame
        → OutputManager.on_imx500_detected()   (display)
        → NetworkManager.report_accident()      (network)
```

IMX500 raw boxes: `[ymin, xmin, ymax, xmax]` normalized to [0,1] when ≤ 1.0; else absolute `[xmin, ymin, xmax, ymax]`.

**`imx500-raw` path (RTSP streaming + software AI):** Opens the IMX500 camera via `picamera2` at `camera.imx500.camera_num` (default 0) without loading any `.rpk` model. Frame path is identical to `picam` mode. `AIManager` runs normally and `StreamManager` streams raw frames to MediaMTX.

### RTSP streaming path

```
FrameBuffer → RTSPStream thread
    └─ StreamHandler.get_latest_with_timestamp()
          ↓ (throttled to stream.fps)
       cv2.resize() if resolution differs
          ↓
       ffmpeg stdin (raw BGR bytes)
          ↓
       MediaMTX (rtsp://localhost:8554/live)
          ↓
       Central Unit pulls rtsp://<node-ip>:8554/live
```

`StreamManager` starts MediaMTX as a subprocess using `configs/mediamtx.yml`, waits 1.5 s for it to boot, then starts `StreamHandler`. If ffmpeg crashes it is restarted automatically with backoff capped at 30 s.

---

## Project Structure

```
Safespace_node/
├── configs/
│   ├── config.yaml          single config file — all settings
│   └── mediamtx.yml         MediaMTX config — RTSP on :8554, single "live" path
├── models/
│   ├── *.pt                 YOLO weights (gitignored / large)
│   ├── *.onnx               ONNX weights
│   └── *.rpk                IMX500 compiled network
├── assets/
│   ├── road_signs_icons/    SVGs used by LaneWidget
│   └── accidents_images/    fallback accident image
├── src/
│   ├── main.py              SafespaceNode orchestrator + CLI entry point
│   ├── managers/
│   │   ├── ai.py            AIManager — inference loop + model registry
│   │   ├── input.py         InputManager — capture loop
│   │   ├── output.py        OutputManager — display bridge
│   │   ├── network.py       NetworkManager — heartbeat + accident + commands
│   │   └── stream.py        StreamManager — MediaMTX subprocess + StreamHandler
│   ├── handlers/
│   │   ├── camera.py        CameraHandler (native / picam / imx500 / imx500-raw)
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
│   │   ├── constants.py     all global constants (API paths, event names, status strings)
│   │   └── failures.py      SafespaceError hierarchy + FailureManager (threshold tracker)
│   └── test_display.py      manual GUI test — no camera/network needed
├── edit_*.py                scratch/experiment files — NOT part of the package
├── requirements.txt         base deps (GPU/CPU desktop)
├── requirements-gpu.txt     extends requirements.txt with torch+CUDA
├── requirements-raspi.txt   Pi deps (PyQt6 from apt, torch CPU)
├── .env.example             ROBOFLOW_API_KEY
└── ARCHITECTURE.md          detailed threading diagrams and optimization notes
```

**Convention for new files:** handlers go in `src/handlers/`, managers in `src/managers/`, utilities in `src/utils/`. New display widgets go in `src/handlers/display/`. Constants go in `src/utils/constants.py`. Never import across the package from outside `src/` — the entry point sets `sys.path`.

---

## Commands

### Install

```bash
# Desktop / laptop (GPU optional)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-gpu.txt   # includes torch CUDA 12.1 + base requirements

# Raspberry Pi — PyQt6 must come from apt, not pip
sudo apt update && sudo apt install -y python3-pyqt6
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements-raspi.txt
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

### RTSP streaming setup (Raspberry Pi)

```bash
# 1. Install ffmpeg
sudo apt install -y ffmpeg

# 2. Download MediaMTX binary (ARM64 for Pi 4/5)
#    https://github.com/bluenviron/mediamtx/releases
#    Extract and place the binary so it's on PATH, or set stream.mediamtx_path in config.yaml

# 3. Set camera mode and enable streaming in configs/config.yaml:
#    camera.model: "imx500-raw"
#    stream.enabled: true

# Central Unit then pulls:  rtsp://<node-ip>:8554/live
```

### Manual display test (no camera or network)

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 src/test_display.py
```

### Lint / format

No linting or formatting configuration exists in this repo (no `.flake8`, `pyproject.toml`, `setup.cfg`). There is no automated test suite — `src/test_display.py` is a manual integration test only.

---

## Configuration

All settings live in `configs/config.yaml`. The `Config` class resolves paths relative to the project root and is accessed with dot-notation:

```python
config.get('camera.fps')          # → 30
config.get_int('node.lanes', 4)   # typed helpers
config.get_float('camera.imx500.confidence', 0.5)
config.get_bool('display.fullscreen', False)
```

### Environment overrides

Three env vars override the YAML at startup:

| Env var | Config key |
|---|---|
| `NODE_ID` | `node.id` |
| `SERVER_URL` | `network.server_url` |
| `LOG_LEVEL` | `logging.level` |

### Key config sections

| Section | Purpose |
|---|---|
| `node.id` | Unique node identifier sent in every network payload |
| `node.lanes` | Number of lane widgets created in the GUI |
| `node.default_speed` | Default speed shown on reset |
| `node.location.lat/long` | Static GPS fallback when SIM808 has no fix |
| `camera.model` | `"native"` / `"picam"` / `"imx500"` (on-chip NPU) / `"imx500-raw"` (plain camera + software AI) |
| `camera.index` | OpenCV capture index for native mode (default 0) |
| `camera.imx500.camera_num` | Picamera2 camera index for IMX500 hardware (default 0, used by `imx500` and `imx500-raw`) |
| `stream.enabled` | Enable RTSP streaming via MediaMTX + ffmpeg |
| `stream.port` | MediaMTX RTSP port (default 8554) |
| `stream.path` | Stream path — Central Unit pulls `rtsp://<node-ip>:<port>/<path>` |
| `stream.fps` | Push rate to MediaMTX (default 15; independent of `camera.fps`) |
| `stream.mediamtx_path` | Path or name of the MediaMTX binary (default `mediamtx`, must be on PATH) |
| `stream.mediamtx_config` | Path to MediaMTX config relative to project root (default `configs/mediamtx.yml`) |
| `ai.models.<name>` | `path`, `type`, `confidence`, `enabled`, `target_classes` |
| `network.server_url` | Central Unit base URL (`http://` or `https://`) |
| `network.ws_path` | Raw WS endpoint appended to server URL, converted to `ws://` |
| `network.accident_cooldown` | Seconds between duplicate accident reports |
| `gps.port` | UART device, e.g. `/dev/ttyAMA0` |
| `display.mode` | `"dev"` (two video feeds + metrics) or `"prod"` (lanes + speed only) |
| `logging.file_logging` | Logs written to `src/logs/safespace.log` (rotating, 5 MB default) |

### External services

- **Central Unit server**: URL set in `network.server_url`. The raw WebSocket URL is auto-derived: `https://` → `wss://`, path appended as `?client=node`.
- **No database** — no local persistence beyond logs.
- **Roboflow** (optional): `ROBOFLOW_API_KEY` env var — only needed if using Roboflow for model download.

---

## Conventions & Gotchas

### Imports and PYTHONPATH

All `src/` modules import each other with bare names (`from utils.config import Config`, not `from src.utils.config`). This requires `PYTHONPATH` to include the project root **and** for `sys.path` to include `src/`. `main.py` adds `os.path.dirname(os.path.abspath(__file__))` (i.e., `src/`) to `sys.path` when run as `__main__`, so the bare imports resolve. Always run from the project root with `PYTHONPATH=$PYTHONPATH:$(pwd)`.

### Qt thread safety — never skip the signal

All Qt widget mutations must happen on the **main thread**. Every cross-thread update goes through a `pyqtSignal`. `MainWindow` defines one signal per update type (`update_lane_signal`, `update_speed_signal`, `set_accident_signal`, `reset_display_signal`, `push_input_frame_signal`, `push_ai_frame_signal`, `update_gps_signal`). Call the public methods (`update_lane()`, `update_speed()`, etc.) from any thread — they emit the signal. **Never call `_update_lane()` / `_update_speed()` / etc. directly from a background thread.**

### Logging pattern

Call `Logger.setup(config.get('logging', {}))` exactly once (done in `SafespaceNode.__init__`). Then create a per-class instance: `self.logger = Logger("ClassName")`. Do not use the root `logging` module directly elsewhere.

### Model path resolution

`AIManager._load_model()` resolves model paths relative to the project root using `Path(__file__).parent.parent.parent`. Paths in `ai.models.<name>.path` should be relative to the project root (e.g., `models/best_MSamir.pt`).

### Adding a new model

1. Add the model file to `models/`.
2. Add an entry under `ai.models` in `configs/config.yaml` with `type`, `path`, `confidence`, `enabled`, `target_classes`.
3. `AIManager` auto-loads all `enabled: true` models at startup; `.pt` → YOLO, `.onnx` → OnnxModel.

### Adding a new WS command

Extend `NetworkManager._on_command()` with a new `elif command_id == "..."` branch. Add the constant to `src/utils/constants.py`.

### FrameBuffer: frame.copy() is inside the lock

`get_latest_with_timestamp()` calls `frame.copy()` while holding `_lock`, which blocks `write_frame()` during the copy. For short frames this is fine; for large resolutions it can cause InputCapture stalls (see ARCHITECTURE.md Risk 3 for a fix).

### Accident payload format

Single detection → `accidentPolygon.points` is a flat list of 4 `{x, y}` dicts. Multiple detections → list of lists. The backend schema changes depending on detection count.

### IMX500 auto-disables software AI — only in `imx500` mode

`camera.model: "imx500"` sets `enable_ai = False` before `AIManager` is constructed — no `.pt`/`.onnx` models are loaded. `camera.model: "imx500-raw"` does **not** do this; software AI runs normally alongside the RTSP stream.

### RTSP stream is a second FrameBuffer consumer

`StreamHandler` calls `get_latest_with_timestamp()` in its own thread, same as `AIManager`. Both are independent readers — neither blocks the other or the camera capture thread. However `frame.copy()` is taken inside the buffer lock, so very high-resolution frames can briefly delay `write_frame()` (see ARCHITECTURE.md Risk 3).

### ffmpeg must be installed separately

`StreamHandler` shells out to `ffmpeg`. It is not in `requirements.txt` (it is a system binary). Install with `sudo apt install ffmpeg` on Pi or `brew install ffmpeg` / system package manager on desktop. If `ffmpeg` is not found the stream thread logs an error and retries with backoff — the rest of the node continues normally.

### MediaMTX binary is not bundled

Download the correct release from https://github.com/bluenviron/mediamtx/releases (arm64 for Pi 4/5, amd64 for desktop). Place it on `PATH` or set `stream.mediamtx_path` to the full path. If MediaMTX fails to start, `StreamHandler` still attempts to connect ffmpeg — it will just fail and retry.

### GPS fallback

`GPSHandler.get_location()` always returns a dict with `{"lat": float, "long": float, "fix": bool}`. When `fix=False` it returns the static coordinates from `node.location.lat/long`. `NetworkManager` logs a debug message in that case but still sends the coordinates.

### `network.register_node()` is a no-op

`NetworkManager.register_node()` is a stub reserved for future server-side implementation. It does nothing currently.

### ONNX model class names

`OnnxModel._extract_names()` parses class names from ONNX custom metadata (`ast.literal_eval`). If the ONNX export did not embed names (non-Ultralytics export), it falls back to generic `class_<id>` labels — `target_classes` filtering will silently fail to match.

### picamera2 / NumPy ABI mismatch

If `picamera2` or `simplejpeg` crash with `numpy.dtype size changed`, the environment has NumPy 2.x. Pin `numpy<2` (already in all requirements files). On Pi, install `python3-picamera2` from `apt` before creating the venv.
