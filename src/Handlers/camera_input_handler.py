"""
Camera Input Handler - Captures frames from a physical camera (native webcam or IMX500).
Produces raw frames for the FrameBuffer.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
from typing import Optional
from cv2.typing import MatLike
from utils.config import Config
from utils.logger import Logger

try:
    import picamera2 as pc2
except ImportError:
    pc2 = None


class CameraInputHandler:
    """Captures frames from a physical camera source."""

    def __init__(self, config: Config):
        self.logger = Logger("CameraInputHandler")
        self.config = config
        self.camera_type: str = self.config.get('camera.model', 'native')
        self.camera = None
        self._running = False

    def start(self) -> bool:
        """Open the camera device. Returns True on success."""
        try:
            if self.camera_type == 'imx500':
                if pc2 is None:
                    raise ImportError("picamera2 is not available in this environment.")
                self.camera = pc2.Picamera2()
                res = self.config.get('camera.resolution', {})
                cam_config = self.camera.create_preview_configuration(
                    main={"size": (res.get('width', 1920), res.get('height', 1080))}
                )
                self.camera.configure(cam_config)
                self.camera.start()
            else:
                index = self.config.get_int('camera.index', 0)
                self.camera = cv2.VideoCapture(index)
                if not self.camera.isOpened():
                    raise RuntimeError(f"Failed to open camera at index {index}")
                # Apply resolution from config
                res = self.config.get('camera.resolution', {})
                if res.get('width'):
                    self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, res['width'])
                if res.get('height'):
                    self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, res['height'])

            self._running = True
            self.logger.info(f"Camera started ({self.camera_type})")
            return True
        except Exception as e:
            self.logger.error(f"Camera start failed: {e}")
            return False

    def read_frame(self) -> Optional[MatLike]:
        """Read a single frame from the camera. Returns None on failure."""
        if not self._running or self.camera is None:
            return None
        try:
            if self.camera_type == 'imx500':
                return self.camera.capture_array()
            else:
                ret, frame = self.camera.read()
                return frame if ret else None
        except Exception as e:
            self.logger.error(f"Frame read failed: {e}")
            return None

    def stop(self):
        """Release the camera device."""
        self._running = False
        if self.camera is None:
            return
        try:
            if self.camera_type == 'imx500':
                self.camera.stop()
            else:
                self.camera.release()
            self.logger.info("Camera released")
        except Exception as e:
            self.logger.error(f"Camera release failed: {e}")
        finally:
            self.camera = None

    @property
    def is_running(self) -> bool:
        return self._running


if __name__ == "__main__":
    config = Config()
    cam = CameraInputHandler(config)
    try:
        if cam.start():
            frame = cam.read_frame()
            print("✓ Frame captured" if frame is not None else "✗ No frame")
        else:
            print("✗ Camera failed to start")
    finally:
        cam.stop()