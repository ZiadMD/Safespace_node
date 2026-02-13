"""
Input Manager - Orchestrates the input source (camera or video) and feeds frames into the buffer.

Runs a capture loop in a background thread:
    [Camera / Video] --read_frame()--> [FrameBuffer]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import time
import threading
from typing import Optional, Union

from utils.config import Config
from utils.logger import Logger
from Handlers.camera_input_handler import CameraInputHandler
from Handlers.video_input_handler import VideoInputHandler
from Handlers.frame_buffer_handler import FrameBufferHandler


class InputManager:
    """
    Manages the input pipeline: source → buffer.
    
    Picks camera or video based on constructor args,
    runs a capture thread that reads frames and writes them into the shared buffer.
    """

    def __init__(self, config: Config, buffer: FrameBufferHandler, video_path: Optional[str] = None):
        """
        Args:
            config: Application configuration.
            buffer: Shared frame buffer that consumers read from.
            video_path: If provided, use video file instead of camera.
        """
        self.logger = Logger("InputManager")
        self.config = config
        self.buffer = buffer

        # Create the appropriate input source
        if video_path:
            self.source: Union[CameraInputHandler, VideoInputHandler] = VideoInputHandler(config, video_path)
            self._source_type = "video"
        else:
            self.source = CameraInputHandler(config)
            self._source_type = "camera"

        self._thread: Optional[threading.Thread] = None
        self._running = False

        # FPS control
        self._target_fps = self.config.get_int('camera.fps', 30)
        self._frame_interval = 1.0 / self._target_fps if self._target_fps > 0 else 0.033

    def start(self) -> bool:
        """Start the input source and begin the capture loop."""
        if self._running:
            self.logger.warning("Input manager already running")
            return True

        if not self.source.start():
            self.logger.error(f"Failed to start {self._source_type} source")
            return False

        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, name="InputCapture", daemon=True)
        self._thread.start()

        self.logger.info(f"Input manager started ({self._source_type} @ {self._target_fps} fps)")
        return True

    def _capture_loop(self):
        """Background loop: read frames from source, push into buffer."""
        while self._running:
            loop_start = time.monotonic()

            frame = self.source.read_frame()

            if frame is not None:
                self.buffer.write_frame(frame)
            else:
                # Source returned None — either EOF (video) or transient error (camera)
                if not self.source.is_running:
                    self.logger.info("Input source ended")
                    self._running = False
                    break
                # Transient failure — brief pause then retry
                time.sleep(0.01)
                continue

            # FPS throttle: sleep the remainder of the frame interval
            elapsed = time.monotonic() - loop_start
            sleep_time = self._frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def stop(self):
        """Stop the capture loop and release the input source."""
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.source.stop()
        self.logger.info("Input manager stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def source_type(self) -> str:
        return self._source_type


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--video", "-v", type=str, default=None, help="Path to video file")
    args = parser.parse_args()

    config = Config()
    buffer = FrameBufferHandler(config)
    mgr = InputManager(config, buffer, video_path=args.video)

    try:
        if mgr.start():
            # Let it run for 2 seconds then report
            time.sleep(2)
            print(f"✓ Source: {mgr.source_type}")
            print(f"  Buffer: {buffer.size}/{buffer.capacity} frames")
            print(f"  Duration: {buffer.duration_seconds:.2f}s")
        else:
            print("✗ Failed to start input")
    finally:
        mgr.stop()
