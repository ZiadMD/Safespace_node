"""
Camera Handler - Manages low-level frame capture using OpenCV.
Runs in a dedicated thread to prevent blocking the GUI or AI logic.
"""
import cv2
import threading
import time
from typing import Optional, Callable
from utils.logger import Logger


class CameraHandler:
    """Handles interaction with the physical camera hardware."""
    
    def __init__(self, config: dict):
        """
        Initialize the camera handler.
        
        Args:
            config: Camera-specific configuration subset
        """
        self.config = config
        self.logger = Logger("CameraHandler")
        self.cap = None
        self.active = False
        self.on_frame_captured: Optional[Callable] = None
        self.thread: Optional[threading.Thread] = None
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.ready = False

    def start(self, callback: Optional[Callable] = None) -> bool:
        """
        Starts the camera capture thread. 
        Note: The actual hardware initialization happens in the background.
        
        Args:
            callback: Optional function to call for each captured frame
        """
        if self.active:
            return True
            
        self.on_frame_captured = callback
        self.active = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        self.logger.info("Camera capture thread spawned.")
        return True

    def capture_frame(self, path: str) -> bool:
        """
        Save the current camera frame to a file.
        
        Args:
            path: Absolute path to save the image
        """
        with self.frame_lock:
            if self.latest_frame is None:
                self.logger.warning("No frame available to capture (Camera might still be initializing)")
                return False
            
            try:
                # Ensure directory exists
                from pathlib import Path
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                
                # imwrite is a bit heavy, but it's now called from its own context
                success = cv2.imwrite(path, self.latest_frame)
                return success
            except Exception as e:
                self.logger.error(f"Failed to save frame: {e}")
                return False

    def stop(self):
        """Cleanly stop the camera capture."""
        self.active = False
        if self.thread:
            self.thread.join(timeout=1.0)
        self.logger.info("Camera stopped")

    def _capture_loop(self):
        """Internal loop for hardware initialization and frame capture."""
        index = self.config.get('index', 0)
        fps = self.config.get('fps', 30)
        width = self.config.get('width', 640)
        height = self.config.get('height', 480)
        
        self.logger.info(f"Initializing camera hardware (Index: {index})...")
        self.cap = cv2.VideoCapture(index)
        
        if not self.cap.isOpened():
            self.logger.error(f"Failed to open camera index {index}")
            self.active = False
            return

        # Configure hardware
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.ready = True
        self.logger.info(f"Camera hardware ready at {width}x{height}")
        
        while self.active:
            ret, frame = self.cap.read()
            if not ret:
                self.logger.warning("Captured empty frame, retrying...")
                time.sleep(0.1)
                continue
            
            # Store frame for snapshot requests
            with self.frame_lock:
                self.latest_frame = frame.copy()
                
            # Invoke callback for any real-time processing (AI/UI)
            if self.on_frame_captured:
                try:
                    self.on_frame_captured(frame)
                except Exception as e:
                    self.logger.error(f"Callback error in camera thread: {e}")
            
            # Frame rate control
            time.sleep(1 / fps)

        # Cleanup hardware on exit
        if self.cap:
            self.cap.release()
            self.cap = None
        self.ready = False
