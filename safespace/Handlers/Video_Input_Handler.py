# This code is for testing the AI detection when camera isn't available

import cv2
from utils.logger import Logger

class VideoInputHandler:
    """Handles video file input for testing purposes."""
    
    def __init__(self, video_path: str):
        """
        Initialize the video input handler.
        
        Args:
            video_path: Path to the video file
        """
        self.video_path = video_path
        self.logger = Logger("VideoInputHandler")
        self.cap = None

    def start(self) -> bool:
        """Start the video capture."""
        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            self.logger.error(f"Failed to open video file: {self.video_path}")
            return False
        self.logger.info(f"Video file opened: {self.video_path}")
        return True

    def read_frame(self):
        """Read the next frame from the video."""
        if self.cap is None:
            self.logger.error("Video capture not started.")
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            self.logger.info("End of video file reached.")
            return None
        
        return frame

    def stop(self):
        """Release the video capture resources."""
        if self.cap is not None:
            self.cap.release()
            self.logger.info("Video capture released.")