"""
Video Handler - Reads frames from a video file.
Same interface as CameraHandler so InputManager can use either.
"""
import cv2
from pathlib import Path
from typing import Optional
from cv2.typing import MatLike

from utils.config import Config
from utils.logger import Logger


class VideoHandler:
    """Reads frames from a video file on disk."""

    def __init__(self, config: Config, video_path: str):
        self.logger = Logger("VideoHandler")
        self.config = config
        self.video_path = str(video_path)
        self.loop: bool = self.config.get_bool('camera.loop_video', True)
        self.cap: Optional[cv2.VideoCapture] = None
        self._running = False

    def start(self) -> bool:
        """Open the video file. Returns True on success."""
        if not Path(self.video_path).exists():
            self.logger.error(f"Video file not found: {self.video_path}")
            return False
        try:
            self.cap = cv2.VideoCapture(self.video_path)
            if not self.cap.isOpened():
                raise RuntimeError(f"Cannot open video: {self.video_path}")
            self._running = True
            self.logger.info(f"Video opened: {self.video_path}")
            return True
        except Exception as e:
            self.logger.error(f"Video start failed: {e}")
            return False

    def read_frame(self) -> Optional[MatLike]:
        """Read the next frame. Loops if enabled. Returns None at EOF."""
        if not self._running or self.cap is None:
            return None

        ret, frame = self.cap.read()

        if not ret:
            if self.loop:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
                if ret:
                    self.logger.debug("Video looped to start")
                    return frame
            self.logger.info("Video playback ended")
            self._running = False
            return None

        return frame

    def stop(self):
        """Release the video capture."""
        self._running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            self.logger.info("Video released")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def fps(self) -> float:
        """Return the native FPS of the video file."""
        if self.cap and self.cap.isOpened():
            return self.cap.get(cv2.CAP_PROP_FPS)
        return 0.0

    @property
    def frame_count(self) -> int:
        """Total number of frames in the video."""
        if self.cap and self.cap.isOpened():
            return int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        return 0
