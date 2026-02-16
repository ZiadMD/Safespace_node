"""
Input Manager — Orchestrates the input source (camera or video) and feeds frames into the buffer.

Runs a capture loop in a background thread:
    [Camera / Video] --read_frame()--> [FrameBuffer]
"""
import time
import threading
from typing import Callable, Optional, Union

from cv2.typing import MatLike

from utils.config import Config
from utils.logger import Logger
from handlers.camera import CameraHandler
from handlers.video import VideoHandler
from handlers.frame_buffer import FrameBuffer

# Type aliases for callbacks
FrameCallback = Callable[[MatLike], None]
DetectionCallback = Callable[[str, dict, MatLike], None]


class InputManager:
    """
    Manages the input pipeline: source → buffer.

    Picks camera or video based on constructor args,
    runs a capture thread that reads frames and writes them into the shared buffer.
    """

    def __init__(
        self,
        config: Config,
        buffer: FrameBuffer,
        video_path: Optional[str] = None,
        on_frame: Optional[FrameCallback] = None,
        on_imx500_detection: Optional[DetectionCallback] = None,
    ):
        """
        Args:
            config: Application configuration.
            buffer: Shared frame buffer that consumers read from.
            video_path: If provided, use video file instead of camera.
            on_frame: Optional callback fired with every captured frame.
                      Signature: (frame: MatLike)
            on_imx500_detection: Optional callback fired when IMX500 detections are available.
                                 Signature: (model_name: str, detections: dict, frame: MatLike)
        """
        self.logger = Logger("InputManager")
        self.config = config
        self.buffer = buffer
        self.on_frame = on_frame
        self.on_imx500_detection = on_imx500_detection

        # Create the appropriate input source
        if video_path:
            self.source: Union[CameraHandler, VideoHandler] = VideoHandler(config, video_path)
            self._source_type = "video"
        else:
            self.source = CameraHandler(config)
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
                if self.on_frame:
                    self.on_frame(frame)
                
                # If using IMX500, fire detection callback with on-chip detections
                if self.on_imx500_detection and hasattr(self.source, 'is_imx500') and self.source.is_imx500:
                    detections = self.source.get_imx500_detections()
                    if detections is not None:
                        self.on_imx500_detection("imx500", detections, frame)
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
