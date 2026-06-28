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

## Wired bring-up (direct Ethernet to the Central Unit)

The Pi connects to the Central Unit (CU) over a **direct Ethernet cable**. A
direct link has no DHCP, so both ends use **static IPs** on a private `/24`.
Traffic going over the cable is an OS **routing** decision — there is no
interface binding in application code.

| Host | Interface | Static IP | Notes |
|---|---|---|---|
| Pi (this node) | `eth0` | `192.168.50.10/24` | no gateway on the link |
| Central Unit | its wired NIC | `192.168.50.1/24` | this is the address in `network.server_url` |

The CU address is a **single config value** — `network.server_url` in
`configs/config.yaml` (default `http://192.168.50.1:5000`). Swap the CU box by
editing that one line, or override at runtime with `SERVER_URL`. No CU IP is
hardcoded anywhere in code.

### Pi side (NetworkManager — Raspberry Pi OS Bookworm+)

Run the helper (idempotent — safe to re-run):

```bash
sudo ./scripts/setup-direct-link.sh
# override defaults if needed:
sudo PI_IP=192.168.50.10 CU_IP=192.168.50.1 IFACE=eth0 ./scripts/setup-direct-link.sh
```

Or do it by hand:

```bash
sudo nmcli connection add type ethernet ifname eth0 con-name direct-link \
     ipv4.method manual ipv4.addresses 192.168.50.10/24 ipv4.never-default yes \
     ipv6.method disabled connection.autoconnect yes
sudo nmcli connection up direct-link
```

`ipv4.never-default yes` (and no gateway) is the important part: the cable gets
an address but never becomes the default route, so internet over Wi-Fi keeps
working. The resulting keyfile lands at
`/etc/NetworkManager/system-connections/direct-link.nmconnection`.

> **Not NetworkManager?** Confirm your Pi's stack first:
> `systemctl is-active NetworkManager dhcpcd systemd-networkd`. On dhcpcd
> (Bullseye and earlier) add a static stanza to `/etc/dhcpcd.conf` instead.

### Central Unit side (Linux / NetworkManager)

```bash
nmcli device status                       # find the CU's wired NIC name (e.g. enp3s0)
sudo nmcli connection add type ethernet ifname <NIC> con-name direct-link \
     ipv4.method manual ipv4.addresses 192.168.50.1/24 ipv4.never-default yes \
     ipv6.method disabled connection.autoconnect yes
sudo nmcli connection up direct-link
```

### Zero-config fallback (link-local / APIPA)

If neither end has a static address, NetworkManager auto-assigns a link-local
`169.254.x.x` address (APIPA) and the two can still reach each other — but those
addresses are not deterministic, so you'd need mDNS (`<host>.local`) to find the
CU. Static IPs are preferred precisely because the CU address must stay fixed in
`network.server_url`.

### Verify the link (run on the Pi)

```bash
nmcli connection show direct-link        # profile is active
ip -4 addr show eth0                      # → inet 192.168.50.10/24
ip route get 192.168.50.1                 # → ... dev eth0 src 192.168.50.10
ping -c3 192.168.50.1                     # CU answers over the cable
```

The `ip route get` line resolving via **`dev eth0`** is the evidence that CU
traffic goes over Ethernet. After starting the node, `logs/safespace.log` should
show node registration (`200`) and heartbeats to the CU.

> A startup **connectivity gate** (block-and-retry until the CU is reachable,
> then continue) and an automatic interface-route report are added on top of the
> diagnostics module — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

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
