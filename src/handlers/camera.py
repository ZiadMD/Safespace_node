"""
Camera Handler - Captures frames from a physical camera (native webcam or IMX500).

Modes:
  - native:  Uses OpenCV VideoCapture (development / laptop).
  - imx500:  Uses picamera2 with the Sony IMX500 AI accelerator (Raspberry Pi production).
             In IMX500 mode the on-chip NPU runs inference and returns detections
             alongside each frame — no separate AI Manager needed.

Produces raw frames for the FrameBuffer.
"""
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, List, Any
from cv2.typing import MatLike

from utils.config import Config
from utils.logger import Logger

try:
    from picamera2 import Picamera2
    from picamera2.devices import IMX500
    from picamera2.devices.imx500 import NetworkIntrinsics
    _HAS_PICAMERA2 = True
except ImportError:
    _HAS_PICAMERA2 = False


class CameraHandler:
    """Captures frames from a physical camera source (native or IMX500)."""

    def __init__(self, config: Config):
        self.logger = Logger("CameraHandler")
        self.config = config
        self.camera_type: str = self.config.get('camera.model', 'native')
        self.camera = None
        self._running = False

        # IMX500-specific
        self._imx500: Any = None
        self._last_detections: Optional[Any] = None

    # ── Start / Stop ──────────────────────────────────────────────

    def start(self) -> bool:
        """Open the camera device. Returns True on success."""
        try:
            if self.camera_type == 'imx500':
                return self._start_imx500()
            else:
                return self._start_native()
        except Exception as e:
            self.logger.error(f"Camera start failed: {e}")
            return False

    def _start_native(self) -> bool:
        """Open a standard USB / laptop camera via OpenCV."""
        index = self.config.get_int('camera.index', 0)
        self.camera = cv2.VideoCapture(index)
        if not self.camera.isOpened():
            raise RuntimeError(f"Failed to open camera at index {index}")

        res = self.config.get('camera.resolution', {})
        if res.get('width'):
            self.camera.set(cv2.CAP_PROP_FRAME_WIDTH, res['width'])
        if res.get('height'):
            self.camera.set(cv2.CAP_PROP_FRAME_HEIGHT, res['height'])

        self._running = True
        self.logger.info("Camera started (native)")
        return True

    def _start_imx500(self) -> bool:
        """Open the IMX500 camera with on-chip AI model."""
        if not _HAS_PICAMERA2:
            raise ImportError(
                "picamera2 is not available. "
                "Install it on Raspberry Pi: sudo apt install python3-picamera2"
            )

        model_path = self.config.get('camera.imx500.model_path', '')
        if not model_path or not Path(model_path).exists():
            raise FileNotFoundError(
                f"IMX500 model not found: {model_path}. "
                "Set 'camera.imx500.model_path' in config.yaml to a valid .rpk file."
            )

        self.logger.info(f"Loading IMX500 model: {model_path}")
        self._imx500 = IMX500(model_path)

        intrinsics = self._imx500.network_intrinsics or NetworkIntrinsics()
        intrinsics.task = "object detection"
        confidence = self.config.get_float('camera.imx500.confidence', 0.5)
        intrinsics.confidence_threshold = confidence
        intrinsics.iou_threshold = self.config.get_float('camera.imx500.iou_threshold', 0.5)
        intrinsics.max_detections = self.config.get_int('camera.imx500.max_detections', 10)
        self._imx500.network_intrinsics = intrinsics

        self.camera = Picamera2(self._imx500.camera_num)
        res = self.config.get('camera.resolution', {})
        cam_config = self.camera.create_preview_configuration(
            main={"size": (res.get('width', 1920), res.get('height', 1080))},
            controls={"FrameRate": self.config.get_int('camera.fps', 30)},
        )
        self.camera.configure(cam_config)
        self.camera.start()

        self._running = True
        self.logger.info(f"Camera started (IMX500, confidence={confidence})")
        return True

    def stop(self):
        """Release the camera device."""
        self._running = False
        if self.camera is None:
            return
        try:
            if self.camera_type == 'imx500':
                self.camera.stop()
                self.camera.close()
            else:
                self.camera.release()
            self.logger.info("Camera released")
        except Exception as e:
            self.logger.error(f"Camera release failed: {e}")
        finally:
            self.camera = None
            self._imx500 = None

    # ── Frame Reading ─────────────────────────────────────────────

    def read_frame(self) -> Optional[MatLike]:
        """Read a single frame. Returns None on failure."""
        if not self._running or self.camera is None:
            return None
        try:
            if self.camera_type == 'imx500':
                return self._read_frame_imx500()
            else:
                ret, frame = self.camera.read()
                return frame if ret else None
        except Exception as e:
            self.logger.error(f"Frame read failed: {e}")
            return None

    def _read_frame_imx500(self) -> Optional[MatLike]:
        """Read a frame from the IMX500 and cache its on-chip detections."""
        metadata = self.camera.capture_metadata()
        frame = self.camera.capture_array()
        try:
            np_outputs = self._imx500.get_outputs(metadata)
            if np_outputs is not None:
                boxes, scores, classes = np_outputs[0], np_outputs[1], np_outputs[2]
                self._last_detections = {
                    "boxes": boxes,
                    "scores": scores,
                    "class_ids": classes.astype(int) if classes is not None else np.array([]),
                }
            else:
                self._last_detections = None
        except Exception as e:
            self.logger.debug(f"IMX500 output parse failed: {e}")
            self._last_detections = None
        return frame

    # ── IMX500 Detection Access ───────────────────────────────────

    def get_imx500_detections(self) -> Optional[dict]:
        """Get the on-chip detections from the last IMX500 frame."""
        if self.camera_type != 'imx500':
            return None
        return self._last_detections

    # ── Properties ────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_imx500(self) -> bool:
        return self.camera_type == 'imx500'
