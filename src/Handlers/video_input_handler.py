"""
Video Input Handler - Reads frames from a video file.
Produces raw frames for the FrameBuffer, same interface as CameraInputHandler.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
from typing import Optional
from cv2.typing import MatLike
from utils.config import Config
from utils.logger import Logger


class VideoInputHandler:
    """Reads frames from a video file on disk."""

    def __init__(self, config: Config, video_path: str):
        """
        Args:
            config: Application configuration.
            video_path: Absolute or relative path to the video file.
        """
        self.logger = Logger("VideoInputHandler")
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
        """
        Read the next frame from the video.
        If looping is enabled, restarts from the beginning when the video ends.
        Returns None when the video is finished (no-loop) or on error.
        """
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
            # Either loop failed or looping is disabled
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


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("video", help="Path to a video file")
    args = parser.parse_args()

    config = Config()
    vid = VideoInputHandler(config, args.video)
    try:
        if vid.start():
            frame = vid.read_frame()
            print(f"✓ Frame captured ({frame.shape})" if frame is not None else "✗ No frame")
            print(f"  FPS: {vid.fps}, Frames: {vid.frame_count}")
        else:
            print("✗ Video failed to open")
    finally:
        vid.stop()
