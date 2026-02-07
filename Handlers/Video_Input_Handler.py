"""Video Input Handler - Reads frames from a video file for testing.

Implements the FrameSource protocol, same interface as CameraHandler.
Used when the --video flag is passed to the node.
"""
import cv2
import numpy as np
from typing import Optional
from pathlib import Path
from utils.logger import Logger


class VideoInputHandler:
    """Handles video file input for testing purposes.
    
    Implements the FrameSource protocol:
        start() -> bool
        read_frame() -> Optional[np.ndarray]
        stop() -> None
    """

    def __init__(self, video_path: str):
        """
        Initialize the video input handler.

        Args:
            video_path: Path to the video file.
        """
        self.video_path = video_path
        self.logger = Logger("VideoInputHandler")
        self.cap: Optional[cv2.VideoCapture] = None
        self.logger.info(f"VideoInputHandler initialized with video: {video_path}")

    # ── FrameSource protocol ──────────────────────────────────────────

    def start(self) -> bool:
        """Open the video file for reading."""
        if not Path(self.video_path).exists():
            self.logger.error(f"Video file not found: {self.video_path}")
            return False

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            self.logger.error(f"Failed to open video file: {self.video_path}")
            return False

        self.logger.info(f"Video file opened: {self.video_path}")
        return True

    def read_frame(self) -> Optional[np.ndarray]:
        """Read the next frame from the video file."""
        if self.cap is None:
            return None

        ret, frame = self.cap.read()
        if not ret:
            return None

        return frame

    def stop(self) -> None:
        """Release the video capture resources."""
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            self.logger.info("Video capture released")