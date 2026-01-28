"""
IO Manager - Orchestrates Camera and Display handlers.
"""
import time
from datetime import datetime
from typing import Optional, Callable
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
