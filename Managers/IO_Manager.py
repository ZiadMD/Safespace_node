"""
IO Manager - Orchestrates Camera/Video and Display handlers.
"""
import time
from datetime import datetime
from typing import Optional, Callable, Union
from queue import Queue
from threading import Lock, Thread
from cv2.typing import MatLike
from Handlers.Camera_Handler import CameraHandler
from Handlers.Video_Input_Handler import VideoInputHandler
from Handlers.Display_Handler import DisplayHandler
from utils.logger import Logger
from utils.config import Config
from utils.constants import ACCIDENT_IMAGES_DIR


class IOManager:
    """Manages the coordination between Input (Camera/Video) and Output (Display) handlers."""
    
    def __init__(self, config: Config, on_manual_trigger: Optional[Callable] = None, 
                 video_path: Optional[str] = None):
        """
        Initialize the IO Manager.
        
        Args:
            config: Unified configuration object
            on_manual_trigger: Callback for UI interactions (e.g. spacebar)
            video_path: Optional path to video file for testing (overrides camera)
        """
        self.config = config
        self.logger = Logger("IOManager")
        self.video_path = video_path
        self._video_thread: Optional[Thread] = None
        self._video_active = False
        
        # Initialize input handler (Video or Camera)
        if video_path:
            self.logger.info(f"Video test mode enabled: {video_path}")
            self.input_handler: Union[CameraHandler, VideoInputHandler] = VideoInputHandler(video_path)
            self.camera = None  # No camera in video mode
        else:
            camera_conf = config.get('camera', {})
            self.input_handler = CameraHandler(camera_conf)
            self.camera = self.input_handler  # Alias for backward compatibility
        
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
        
        if self.video_path:
            # Video test mode
            if not self.input_handler.start():
                self.logger.error("Failed to start video input")
            else:
                self._video_active = True
                self._video_thread = Thread(target=self._video_loop, daemon=True)
                self._video_thread.start()
                self.logger.info("Video playback started")
        else:
            # Camera mode
            if not self.input_handler.start():
                self.logger.warning("Camera failed to start, proceeding in display-only mode")
            
        # Start display (blocks)
        self.display.start()

    def _video_loop(self):
        """Internal loop for reading video frames and invoking callbacks."""
        fps = self.config.get('camera', {}).get('fps', 30)
        loop_video = self.config.get('camera', {}).get('loop_video', True)
        
        while self._video_active:
            frame = self.input_handler.read_frame()
            
            if frame is None:
                if loop_video:
                    # Restart video from beginning
                    self.input_handler.stop()
                    self.input_handler.start()
                    self.logger.info("Video looped back to start")
                    continue
                else:
                    self.logger.info("Video playback finished")
                    break
            
            # Update latest frame
            with self._frame_lock:
                self._latest_frame = frame.copy()
            
            # Notify AI Manager if callback is registered
            if self._frame_callback:
                try:
                    self._frame_callback(frame)
                except Exception as e:
                    self.logger.error(f"Callback error in video thread: {e}")
            
            # Frame rate control
            time.sleep(1 / fps)

    def get_accident_snapshot(self) -> Optional[str]:
        """
        Captures a frame from the active input and saves it to the assets directory.
        
        Returns:
            Absolute path to the saved image or None if failed.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"accident_{timestamp}.jpg"
        save_path = str(ACCIDENT_IMAGES_DIR / filename)
        
        if self.video_path:
            # Video mode - save from latest frame
            import cv2
            from pathlib import Path
            with self._frame_lock:
                if self._latest_frame is not None:
                    Path(save_path).parent.mkdir(parents=True, exist_ok=True)
                    if cv2.imwrite(save_path, self._latest_frame):
                        return save_path
            return None
        else:
            # Camera mode
            if self.camera and self.camera.capture_frame(save_path):
                return save_path
            return None

    def stop(self):
        """Cleanly stops all handlers."""
        self._video_active = False
        if self._video_thread:
            self._video_thread.join(timeout=1.0)
        self.input_handler.stop()
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
