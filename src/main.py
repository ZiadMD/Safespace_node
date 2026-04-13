#!/usr/bin/env python3
"""
Safespace Node v2 — Main Entry Point

Orchestrates the system using a supervisor-based architecture:
    1. Loads config
    2. Allocates shared memory
    3. Creates message bus
    4. Spawns capture process (separate OS process)
    5. Spawns inference process (separate OS process, optional)
    6. Starts network service (asyncio in thread)
    7. Starts supervisor (health monitoring in thread)
    8. Runs Qt display on main thread (or headless loop)

Usage:
    python main.py                        # normal boot from config
    python main.py --video path/to.mp4    # use a video file instead of camera
    python main.py --no-ai                # disable AI inference
    python main.py --no-display           # headless mode (no GUI)
    python main.py --no-network           # offline mode (no server)
"""
import os
import sys
import signal
import argparse
import time
import multiprocessing as mp
from pathlib import Path

# Add src/ to Python path
sys.path.insert(0, str(Path(__file__).parent))

from core.config import Config
from core.logger import Logger
from core.message_bus import MessageBus
from core.shared_memory import SharedFrameSlots
from core.node_state import NodeState, Mode
from core.supervisor import NodeSupervisor
from core.constants import TOPIC_SHUTDOWN, TOPIC_DETECTION, TOPIC_MODE_CHANGED


def parse_args():
    parser = argparse.ArgumentParser(description="Safespace Node v2")
    parser.add_argument("--video", type=str, default=None, help="Video file path (test mode)")
    parser.add_argument("--no-ai", action="store_true", help="Disable AI inference")
    parser.add_argument("--no-display", action="store_true", help="Headless mode")
    parser.add_argument("--no-network", action="store_true", help="Offline mode")
    parser.add_argument("--config", type=str, default=None, help="Config file path")
    return parser.parse_args()


def main():
    args = parse_args()

    # ── 1. Config + Logging ──────────────────────────────────────
    config = Config(args.config)
    Logger.setup(config.get('logging', {}))
    logger = Logger("SafespaceNode")
    logger.info("Initializing Safespace Node v2...")

    # Check for env-based overrides
    if os.environ.get('SAFESPACE_NO_DISPLAY') == '1':
        args.no_display = True

    # IMX500 mode disables software AI
    camera_model = config.get('camera.model', 'native')
    enable_ai = not args.no_ai and camera_model != 'imx500'
    enable_display = not args.no_display
    enable_network = not args.no_network

    if camera_model == 'imx500':
        logger.info("IMX500 mode — on-chip inference, software AI disabled")
    if args.video:
        logger.info(f"Video test mode: {args.video}")

    # ── 2. Shared Memory ─────────────────────────────────────────
    width = config.get_int('camera.resolution.width', 640)
    height = config.get_int('camera.resolution.height', 640)
    channels = 3
    num_slots = config.get_int('buffer.num_slots', 4)

    shared_slots = SharedFrameSlots(width, height, channels, num_slots)
    logger.info(f"Shared memory ready ({num_slots} slots, {width}×{height})")

    # ── 3. Message Bus ────────────────────────────────────────────
    bus = MessageBus()

    # ── 4. Node State ─────────────────────────────────────────────
    state = NodeState()

    # ── 5. Stop Event ─────────────────────────────────────────────
    stop_event = mp.Event()

    # Config file path for child processes
    config_path = args.config
    if not config_path:
        config_path = str(Path(__file__).parent.parent / "configs" / "config.yaml")

    # ── 6. Spawn Capture Process ──────────────────────────────────
    from capture.process import capture_process_entry

    capture_proc = mp.Process(
        target=capture_process_entry,
        args=(
            config_path,
            shared_slots.shm_name,
            width, height, channels, num_slots,
            bus,
            args.video,
            stop_event,
        ),
        name="CaptureProcess",
        daemon=True,
    )
    capture_proc.start()
    logger.info(f"Capture process started (pid={capture_proc.pid})")

    # ── 7. Spawn Inference Process (optional) ─────────────────────
    ai_proc = None
    ai_factory = None

    if enable_ai:
        from inference.process import inference_process_entry

        def _create_ai_process():
            p = mp.Process(
                target=inference_process_entry,
                args=(
                    config_path,
                    shared_slots.shm_name,
                    width, height, channels, num_slots,
                    bus,
                    stop_event,
                ),
                name="InferenceProcess",
                daemon=True,
            )
            return p

        ai_factory = _create_ai_process
        ai_proc = _create_ai_process()
        ai_proc.start()
        logger.info(f"Inference process started (pid={ai_proc.pid})")

    # ── 8. Network Service (optional) ─────────────────────────────
    network = None
    if enable_network:
        from network.service import NetworkService

        network = NetworkService(config, state, bus, shared_slots)
        network.start()
        logger.info("Network service started")

    # ── 9. Supervisor ─────────────────────────────────────────────
    supervisor = NodeSupervisor(config, state, bus, ai_factory)
    supervisor.capture_process = capture_proc
    supervisor.ai_process = ai_proc
    supervisor.start()
    logger.info("Supervisor started")

    # ── 10. Signal Handling ───────────────────────────────────────
    def _shutdown(signum=None, frame=None):
        logger.info("Shutdown signal received")
        stop_event.set()
        bus.publish(TOPIC_SHUTDOWN, {"reason": "signal"})

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ── 11. Display or Headless Loop ──────────────────────────────
    try:
        if enable_display:
            from display.app import DisplayApp

            display = DisplayApp(
                config, shared_slots, bus,
                on_manual_trigger=lambda: bus.publish(TOPIC_DETECTION, {
                    "model_name": "manual",
                    "num_detections": 1,
                    "frame_id": shared_slots.latest_frame_id,
                    "timestamp": time.time(),
                    "xyxy": [],
                    "confidence": [],
                    "class_id": [],
                }),
            )
            logger.info("Starting display (Qt event loop)...")
            display.start()  # blocks until window closed
        else:
            logger.info("Headless mode — press Ctrl+C to stop")
            while not stop_event.is_set():
                time.sleep(1)

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt")
    finally:
        # ── Cleanup ───────────────────────────────────────────────
        logger.info("Shutting down...")
        stop_event.set()
        supervisor.stop()

        if network:
            network.stop()

        # Wait for child processes
        if ai_proc and ai_proc.is_alive():
            ai_proc.terminate()
            ai_proc.join(timeout=5)
        if capture_proc.is_alive():
            capture_proc.terminate()
            capture_proc.join(timeout=5)

        bus.close()
        shared_slots.close()
        logger.info("Safespace Node stopped.")


if __name__ == "__main__":
    # Use 'spawn' for clean child processes (required on some Linux configs)
    mp.set_start_method("fork", force=True)
    main()
