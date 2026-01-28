# Safespace Node

Safespace Node is a robust hardware-orchestration layer designed for edge-based road safety monitoring. It manages high-speed camera capture, real-time GUI visualization, and dual-mode communication with the Safespace Central Unit.

## 🏗 Architecture

The system follows a strict **Manager-Handler** design pattern to ensure clean decoupling between high-level business logic and low-level hardware interactions.

-   **SafespaceNode (Orchestrator)**: The primary entry point. Manages the high-level application lifecycle and state transitions.
-   **Managers**: Synchronize complex operations across multiple handlers (e.g., `IOManager`, `NetworkManager`).
-   **Handlers**: Low-level implementation wrappers for specific hardware or protocols (e.g., `CameraHandler`, `DisplayHandler`, `SocketHandler`).
-   **Utils**: shared infrastructure for granular configuration, dual-sink logging, and failure resilience.

## 🛠 Features

-   **High-Performance Vision**: Threaded OpenCV capture with zero-lag startup (hardware initialization happens in the background).
-   **Pro-Grade GUI**: PyQt6 dashboard with SVG rendering, automatic aspect-ratio scaling (16:9), and dark-mode aesthetics.
-   **Hybrid Networking**:
    *   **WebSockets (Socket.io)**: Real-time heartbeats and receiving road instructions from the Central Unit.
    *   **HTTP POST (Multipart)**: Reliable, specification-compliant upload of accident metadata and high-res snapshots.
-   **Granular Configuration**: Domain-specific settings (node, network, camera, display) decentralized into manageable JSON files.
-   **State-Driven Logic**: "Awaiting Confirmation" lock ensures the node remains in sync with the Central Unit's decisions.

## 🚀 Getting Started

### 1. Setup Environment
```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configuration
The application automatically merges all JSON files found in `safespace/configs/`. Customize your node by editing:
- `configs/node.json`: ID and GPS coordinates.
- `configs/network.json`: Central Unit URL and heartbeat intervals.
- `configs/camera.json`: Frame rate and resolution.
- `configs/display.json`: Window dimensions.

### 3. Running
```bash
# Run with python path pointing to root
export PYTHONPATH=$PYTHONPATH:$(pwd)
python3 safespace/main.py
```

## ⌨️ Controls
- **Spacebar**: Trigger a manual accident report. The node will capture a frame and wait for server confirmation.

## 📂 Project Structure
- `safespace/Managers/`: High-level orchestration.
- `safespace/Handlers/`: Low-level implementation.
- `safespace/utils/`: Configuration, Loggers, Constants, and Failure Management.
- `safespace/assets/`: UI Icons and captured accident snapshots.
- `safespace/configs/`: JSON configuration files.
- `logs/`: Rotating application logs.
