# Safespace Node — Architecture Reference

This document is the authoritative reference for the internal design of Safespace Node. `CLAUDE.md` (repo root) is the AI-assistant entry point and links here for depth.

---

## Layer diagram

```
SafespaceNode  (src/main.py)
├── GPSHandler           SIM808 UART → live lat/long
├── FrameBuffer          thread-safe deque ring buffer (shared)
├── InputManager
│   ├── CameraHandler    picam / imx500 / imx500-raw
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

---

## Threading model

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

---

## Core data flow

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

---

## IMX500 camera modes

| `camera.model` | On-chip NPU | Software AI | RTSP stream |
|---|---|---|---|
| `imx500` | ✓ loads `.rpk` | ✗ disabled | optional |
| `imx500-raw` | ✗ no model loaded | ✓ enabled | ✓ primary use case |
| `picam` | ✗ | ✓ | optional |

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

---

## RTSP streaming path

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

`StreamManager` starts MediaMTX as a subprocess using the config at `stream.mediamtx_config`, waits 1.5 s for it to boot, then starts `StreamHandler`. If ffmpeg crashes it is restarted automatically with backoff capped at 30 s.

---

## Known risks and gotchas

### FrameBuffer: `frame.copy()` is inside the lock

`get_latest_with_timestamp()` calls `frame.copy()` while holding `_lock`, which blocks `write_frame()` during the copy. For short frames this is fine; for large resolutions it can cause InputCapture stalls. Fix: copy the reference, release the lock, then copy outside.

### RTSP stream is a second FrameBuffer consumer

`StreamHandler` calls `get_latest_with_timestamp()` in its own thread, same as `AIManager`. Both are independent readers — neither blocks the other. However `frame.copy()` inside the lock means very high-resolution frames can briefly delay `write_frame()`.

### Accident payload format

Single detection → `accidentPolygon.points` is a flat list of 4 `{x, y}` dicts. Multiple detections → list of lists. The backend schema changes depending on detection count.

### picamera2 / NumPy ABI mismatch

If `picamera2` or `simplejpeg` crash with `numpy.dtype size changed`, the environment has NumPy 2.x. Pin `numpy<2` (already in `requirements.txt`). On Pi, install `python3-picamera2` from `apt` before creating the venv.

### ffmpeg must be installed separately

`StreamHandler` shells out to `ffmpeg`. Install with `sudo apt install ffmpeg`. If `ffmpeg` is not found the stream thread logs an error and retries with backoff — the rest of the node continues normally.

### MediaMTX binary is not bundled

Download from https://github.com/bluenviron/mediamtx/releases (arm64 for Pi 4/5). Place it on PATH or set `stream.mediamtx_path` to the full path.

### GPS fallback

`GPSHandler.get_location()` always returns `{"lat": float, "long": float, "fix": bool}`. When `fix=False` it returns the static coordinates from `node.location.lat/long`.

### ONNX model class names

`OnnxModel._extract_names()` parses class names from ONNX custom metadata (`ast.literal_eval`). If names were not embedded at export time, it falls back to `class_<id>` labels — `target_classes` filtering will silently fail to match.

---

## Qt thread safety — never skip the signal

All Qt widget mutations must happen on the **main thread**. Every cross-thread update goes through a `pyqtSignal`. `MainWindow` defines one signal per update type. Call the public methods (`update_lane()`, `update_speed()`, etc.) from any thread — they emit the signal. **Never call `_update_lane()` / `_update_speed()` / etc. directly from a background thread.**

## Logging pattern

Call `Logger.setup(config.get('logging', {}))` exactly once (done in `SafespaceNode.__init__`). Then create a per-class instance: `self.logger = Logger("ClassName")`. Do not use the root `logging` module directly elsewhere.

## Model path resolution

`AIManager._load_model()` resolves model paths relative to the project root using `Path(__file__).parent.parent.parent`. Paths in `ai.models.<name>.path` should be relative to the project root (e.g., `models/best_MSamir.pt`).

## Adding a new model

1. Add the model file to `models/`.
2. Add an entry under `ai.models` in `configs/config.yaml` with `type`, `path`, `confidence`, `enabled`, `target_classes`.
3. `AIManager` auto-loads all `enabled: true` models at startup; `.pt` → YOLO, `.onnx` → OnnxModel.

## Adding a new WS command

Extend `NetworkManager._on_command()` with a new `elif command_id == "..."` branch. Add the constant to `src/utils/constants.py`.
