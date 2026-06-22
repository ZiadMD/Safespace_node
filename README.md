# Safespace Node

Edge-based road safety monitoring system running on a Raspberry Pi with a Sony IMX500 AI camera. Captures video, runs accident-detection models, streams an RTSP feed, and communicates with the Safespace Central Unit via Socket.IO and raw WebSockets.

For architecture details see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Requirements

- Raspberry Pi OS (64-bit)
- Sony IMX500 camera (or standard Pi camera in `picam` mode)
- ffmpeg (`sudo apt install ffmpeg`)
- MediaMTX binary — download from https://github.com/bluenviron/mediamtx/releases (arm64)

---

## Install

PyQt6 and picamera2 must come from apt (pip source-builds fail on ARM):

```bash
sudo apt update
sudo apt install -y python3-pyqt6 python3-picamera2 ffmpeg
```

Create the venv with system packages visible, then install the remaining deps:

```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Configure

All settings live in a single file: `configs/config.yaml`.

Key sections:

| Section | What to set |
|---|---|
| `node` | Unique node ID, lane count, static GPS coordinates |
| `camera.model` | `imx500-raw` (default), `imx500`, or `picam` |
| `stream` | RTSP enabled/disabled, MediaMTX binary path |
| `network.server_url` | Central Unit base URL |
| `ai.models` | Model file paths, confidence thresholds, enabled flags |

Three environment variables override YAML at startup:

| Env var | Config key |
|---|---|
| `NODE_ID` | `node.id` |
| `SERVER_URL` | `network.server_url` |
| `LOG_LEVEL` | `logging.level` |

---

## Run

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)

# Default (uses config.yaml settings)
python3 src/main.py

# Use a video file instead of camera (dev/test)
python3 src/main.py --video path/to/video.mp4

# Disable individual subsystems
python3 src/main.py --no-ai        # skip model inference
python3 src/main.py --no-display   # headless
python3 src/main.py --no-network   # offline
python3 src/main.py --no-stream    # disable RTSP
```

**GUI controls:** Spacebar — manual accident report. Escape — close window.

**Logs** are written to `logs/safespace.log` (rotating, 5 MB, project root).

---

## RTSP streaming

When `stream.enabled: true` in config.yaml the node:
1. Starts MediaMTX (path set in `stream.mediamtx_path`)
2. Pushes frames via ffmpeg to `rtsp://localhost:8554/live`

The Central Unit then pulls `rtsp://<node-ip>:8554/live`.

---

## Project structure

```
Safespace_node/
├── configs/
│   ├── config.yaml          single config file — all settings
│   └── mediamtx.yml         MediaMTX config — RTSP on :8554
├── docs/
│   └── ARCHITECTURE.md      threading diagrams, data flow, gotchas
├── models/
│   ├── *.pt                 YOLO weights
│   ├── *.onnx               ONNX weights
│   └── *.rpk                IMX500 compiled networks
├── assets/
│   └── road_signs_icons/    SVGs used by the lane widget
├── logs/                    rotating log output (created at runtime)
├── src/
│   ├── main.py              SafespaceNode orchestrator + CLI entry point
│   ├── managers/            high-level orchestration (ai, input, output, network, stream)
│   ├── handlers/            low-level I/O wrappers (camera, video, socket, display, …)
│   └── utils/               config, logger, constants, failure management
├── requirements.txt         pip deps (PyQt6 + picamera2 come from apt)
└── CLAUDE.md                AI-assistant context and conventions
```

---

## Manual display test (no camera or network)

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 src/test_display.py
```
