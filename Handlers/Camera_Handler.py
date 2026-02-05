"""
Camera Handler - Manages low-level frame capture using Picamera2 for IMX500.
Runs in a dedicated thread to prevent blocking the GUI or AI logic.
"""
import threading
import time
import numpy as np
from typing import Optional, Callable
from utils.logger import Logger

try:
    from picamera2 import Picamera2
    PICAMERA_AVAILABLE = True
except ImportError:
    PICAMERA_AVAILABLE = False

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False

# IMX500 warm-up time in seconds (AI camera needs longer than regular Pi cameras)
IMX500_WARMUP_SECONDS = 3.0
# Max consecutive empty frames before attempting a camera restart
MAX_EMPTY_FRAMES = 50


class CameraHandler:
    """Handles interaction with the IMX500 camera hardware via Picamera2."""
    
    def __init__(self, config: dict):
        """
        Initialize the camera handler.
        
        Args:
            config: Camera-specific configuration subset
        """
        self.config = config
        self.logger = Logger("CameraHandler")
        self.picam2 = None
        self.active = False
        self.on_frame_captured: Optional[Callable] = None
        self.thread: Optional[threading.Thread] = None
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.ready = False
        
        if not PICAMERA_AVAILABLE:
            self.logger.error("Picamera2 not available. Install with: sudo apt install python3-picamera2")

    def start(self, callback: Optional[Callable] = None) -> bool:
        """
        Starts the camera capture thread.
        Note: The actual hardware initialization happens in the background.
        
        Args:
            callback: Optional function to call for each captured frame
        """
        if not PICAMERA_AVAILABLE:
            self.logger.error("Cannot start: Picamera2 not installed")
            return False
            
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
                from pathlib import Path
                Path(path).parent.mkdir(parents=True, exist_ok=True)
                
                if CV2_AVAILABLE:
                    # Convert RGB to BGR for OpenCV
                    bgr_frame = cv2.cvtColor(self.latest_frame, cv2.COLOR_RGB2BGR)
                    success = cv2.imwrite(path, bgr_frame)
                else:
                    # Fallback to PIL
                    from PIL import Image
                    img = Image.fromarray(self.latest_frame)
                    img.save(path)
                    success = True
                return success
            except Exception as e:
                self.logger.error(f"Failed to save frame: {e}")
                return False

    def stop(self):
        """Cleanly stop the camera capture."""
        self.active = False
        if self.thread:
            self.thread.join(timeout=5.0)
        self.logger.info("Camera stopped")

    def _init_camera(self, width: int, height: int) -> bool:
        """
        Initialize the IMX500 camera hardware.
        
        Returns:
            True if camera initialized successfully
        """
        try:
            # Close existing instance if any
            if self.picam2:
                try:
                    self.picam2.stop()
                    self.picam2.close()
                except Exception:
                    pass
                self.picam2 = None

            self.picam2 = Picamera2()
            
            # Log available sensor modes for debugging
            sensor_modes = self.picam2.sensor_modes
            self.logger.info(f"Available sensor modes: {sensor_modes}")
            
            # Configure for video/preview capture
            config = self.picam2.create_preview_configuration(
                main={"size": (width, height), "format": "RGB888"}
            )
            self.picam2.configure(config)
            self.picam2.start()
            
            # IMX500 AI camera needs significantly more warm-up time
            self.logger.info(f"Waiting {IMX500_WARMUP_SECONDS}s for IMX500 warm-up...")
            time.sleep(IMX500_WARMUP_SECONDS)
            
            # Drain initial (potentially empty) frames
            for _ in range(10):
                self.picam2.capture_array("main")
                time.sleep(0.05)
            
            self.logger.info(f"IMX500 camera initialized at {width}x{height}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize IMX500 camera: {e}")
            return False

    def _is_valid_frame(self, frame) -> bool:
        """Check whether a captured frame contains actual image data."""
        if frame is None:
            return False
        if not isinstance(frame, np.ndarray):
            return False
        if frame.size == 0:
            return False
        # Reject fully black frames (sensor not streaming yet)
        if frame.max() == 0:
            return False
        return True

    def _capture_loop(self):
        """Internal loop for hardware initialization and frame capture."""
        fps = self.config.get('fps', 30)
        width = self.config.get('width', 640)
        height = self.config.get('height', 480)
        
        self.logger.info("Initializing IMX500 camera hardware...")
        
        if not self._init_camera(width, height):
            self.active = False
            return
        
        self.ready = True
        self.logger.info(f"IMX500 camera ready at {width}x{height} @ {fps}fps")
        
        frame_interval = 1.0 / fps
        empty_frame_count = 0
        
        while self.active:
            try:
                frame = self.picam2.capture_array("main")
                
                if not self._is_valid_frame(frame):
                    empty_frame_count += 1
                    if empty_frame_count == 1:
                        self.logger.warning("Captured empty frame, waiting for camera stream...")
                    
                    if empty_frame_count >= MAX_EMPTY_FRAMES:
                        self.logger.warning(
                            f"{MAX_EMPTY_FRAMES} consecutive empty frames. Restarting camera..."
                        )
                        self.ready = False
                        if not self._init_camera(width, height):
                            self.logger.error("Camera restart failed, stopping capture.")
                            break
                        self.ready = True
                        empty_frame_count = 0
                    
                    time.sleep(0.1)
                    continue
                
                # Valid frame received
                if empty_frame_count > 0:
                    self.logger.info(
                        f"Camera stream recovered after {empty_frame_count} empty frame(s). "
                        f"Frame shape: {frame.shape}, dtype: {frame.dtype}"
                    )
                    empty_frame_count = 0
                
                # Store frame for snapshot requests
                with self.frame_lock:
                    self.latest_frame = frame.copy()
                    
                # Invoke callback for real-time processing (AI/UI)
                if self.on_frame_captured:
                    try:
                        self.on_frame_captured(frame)
                    except Exception as e:
                        self.logger.error(f"Callback error in camera thread: {e}")
                
                time.sleep(frame_interval)
                
            except Exception as e:
                self.logger.warning(f"Frame capture error: {e}, retrying...")
                time.sleep(0.5)

        # Cleanup hardware on exit
        if self.picam2:
            try:
                self.picam2.stop()
                self.picam2.close()
            except Exception as e:
                self.logger.warning(f"Error during camera cleanup: {e}")
            self.picam2 = None
        self.ready = False