"""
IO Manager - Orchestrates Camera and Display handlers.
"""
import time
from datetime import datetime
from typing import Optional, Callable
from queue import Queue
from threading import Lock
from cv2.typing import MatLike
from Handlers.Camera_Handler import CameraHandler
from Handlers.Display_Handler import DisplayHandler
from utils.logger import Logger
from utils.config import Config
from utils.constants import ACCIDENT_IMAGES_DIR


class IOManager:
    """Manages the coordination between Input (Camera) and Output (Display) handlers."""
    
    def __init__(self, config: Config, on_manual_trigger: Optional[Callable] = None):
        """
        Initialize the IO Manager.
        
        Args:
            config: Unified configuration object
            on_manual_trigger: Callback for UI interactions (e.g. spacebar)
        """
        self.config = config
        self.logger = Logger("IOManager")
        
        # Initialize Handlers
        camera_conf = config.get('camera', {})
        self.camera = CameraHandler(camera_conf)
        
        self.display = DisplayHandler(config, on_manual_trigger=on_manual_trigger)
        
        # Frame sharing for AI Manager
        self._latest_frame: Optional[MatLike] = None
        self._frame_lock = Lock()
        self._frame_callback: Optional[Callable[[MatLike], None]] = None

    def set_frame_callback(self, callback: Callable[[MatLike], None]):
        """
        Register a callback to be invoked when a new frame is available.
        
        Args:
            callback: Function that receives the new frame (used by AI Manager)
        """
        self._frame_callback = callback

    def get_latest_frame(self) -> Optional[MatLike]:
        """
        Thread-safe method to get the most recent frame.
        
        Returns:
            The latest frame or None if no frame is available.
        """
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def _on_new_frame(self, frame: MatLike):
        """
        Internal handler called when camera captures a new frame.
        Updates the latest frame and notifies AI Manager.
        """
        with self._frame_lock:
            self._latest_frame = frame
        
        # Notify AI Manager if callback is registered
        if self._frame_callback:
            self._frame_callback(frame)

    def start(self):
        """Starts the IO components."""
        self.logger.info("Starting IO components...")
        
        # Start camera capture immediately as requested
        if not self.camera.start():
            self.logger.warning("Camera failed to start, proceeding in display-only mode")
            
        # Start display (blocks)
        self.display.start()

    def get_accident_snapshot(self) -> Optional[str]:
        """
        Captures a frame from the active camera and saves it to the assets directory.
        
        Returns:
            Absolute path to the saved image or None if failed.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"accident_{timestamp}.jpg"
        save_path = str(ACCIDENT_IMAGES_DIR / filename)
        
        if self.camera.capture_frame(save_path):
            return save_path
        return None

    def stop(self):
        """Cleanly stops all handlers."""
        self.camera.stop()
        self.logger.info("IO Manager stopped")

    # Bridge methods for display control (called by main orchestrator)
    def update_status(self, lane_index: int, status: str):
        self.display.update_lane_status(lane_index, status)

    def update_speed(self, limit: int):
        self.display.update_speed_limit(limit)

    def toggle_alert(self, active: bool):
        self.display.set_accident_alert(active)
        
    def reset_display(self):
        self.display.reset_display()
