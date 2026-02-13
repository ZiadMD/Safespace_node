"""
Safespace Node - Main Orchestrator.

Wires together:
    InputManager  (camera/video → buffer)
    AIManager     (buffer → inference → detection callbacks)
    
Future:
    NetworkManager (report accidents to central unit)
    OutputManager  (display / LED signs)
"""
import sys
import os
import signal
import argparse
import time

from utils.config import Config
from utils.logger import Logger
from Handlers.frame_buffer_handler import FrameBufferHandler
from Managers.input_manager import InputManager
from Managers.ai_manager import AIManager


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Safespace Node - Road Safety Monitoring System")
    parser.add_argument(
        '--video', '-v',
        type=str,
        default=None,
        help='Path to video file for testing (bypasses camera)'
    )
    parser.add_argument(
        '--no-ai',
        action='store_true',
        help='Disable AI detection (run without model inference)'
    )
    return parser.parse_args()


class SafespaceNode:
    """
    Safespace Node Orchestrator.
    
    Lifecycle:
        1. Config + Logger
        2. FrameBuffer (shared)
        3. InputManager → fills buffer from camera/video
        4. AIManager → pulls from buffer, runs models, fires callbacks
    """

    def __init__(self, video_path: str = None, enable_ai: bool = True):
        # 1. Configuration & Logging
        self.config = Config()
        Logger.setup(self.config.get('logging', {}))
        self.logger = Logger("SafespaceNode")
        self.logger.info("Initializing Safespace Node...")

        if video_path:
            self.logger.info(f"Video test mode: {video_path}")
        if not enable_ai:
            self.logger.info("AI detection disabled")

        # 2. Shared Frame Buffer
        self.buffer = FrameBufferHandler(self.config)

        # 3. Input Manager (camera or video → buffer)
        self.input = InputManager(self.config, self.buffer, video_path=video_path)

        # 4. AI Manager (buffer → inference → callbacks)
        self.ai = None
        if enable_ai:
            self.ai = AIManager(
                self.config,
                self.buffer,
                on_detection=self._on_ai_detection,
            )
            self.logger.info(f"AI Manager ready — models: {self.ai.loaded_models}")

        # Lifecycle
        self.running = False
        self._setup_signals()

    def _setup_signals(self):
        """Handle OS signals for graceful shutdown."""
        def handler(sig, frame):
            self.logger.info("Shutdown signal received")
            self.stop()
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def start(self):
        """Start all services and enter the main loop."""
        self.logger.info("Starting Safespace Node...")

        # Start input pipeline
        if not self.input.start():
            self.logger.error("Input source failed to start — exiting")
            return

        # Start AI inference loop
        if self.ai:
            self.ai.start()

        self.running = True
        self.logger.info("Safespace Node is running. Press Ctrl+C to stop.")

        try:
            while self.running:
                # Main thread heartbeat — keep alive
                if not self.input.is_running:
                    self.logger.info("Input source stopped — shutting down")
                    break
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    def stop(self):
        """Cleanly shutdown all services."""
        if not self.running:
            return
        self.running = False
        self.logger.info("Stopping Safespace Node...")

        if self.ai:
            self.ai.stop()
        self.input.stop()

        self.logger.info("Safespace Node stopped.")

    # ── Callbacks ─────────────────────────────────────────────────

    def _on_ai_detection(self, model_name: str, detections, frame):
        """
        Called by AIManager when a model produces detections.
        
        Args:
            model_name: Name of the model (e.g. "accident_detection")
            detections: supervision.Detections object
            frame: The frame where detection occurred
        """
        self.logger.warning(
            f"AI DETECTION [{model_name}]: {len(detections)} object(s) detected"
        )

        # TODO: Report to central unit via NetworkManager
        # TODO: Save snapshot / clip from buffer
        # TODO: Update display via OutputManager


if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    args = parse_args()
    node = SafespaceNode(
        video_path=args.video,
        enable_ai=not args.no_ai,
    )
    node.start()
