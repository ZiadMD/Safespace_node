"""
Capture Sources — Camera and video input abstraction.

Combined CameraSource + VideoSource with a factory function.
Both implement the same interface: start() / read_frame() / stop().
"""
import cv2
import numpy as np
from pathlib import Path
from typing import Optional, Any
from cv2.typing import MatLike

from core.config import Config
from core.logger import Logger

try:
    from picamera2 import Picamera2
    from picamera2.devices import IMX500
    from picamera2.devices.imx500 import NetworkIntrinsics
    _HAS_PICAMERA2 = True
    _PICAMERA2_IMPORT_ERROR = None
except Exception as exc:
    _HAS_PICAMERA2 = False
    _PICAMERA2_IMPORT_ERROR = exc


def create_source(config: Config, video_path: Optional[str] = None):
    """
    Factory: create the appropriate input source.

    Returns a CameraSource or VideoSource based on config/args.
    """
    if video_path:
        return VideoSource(config, video_path)
    return CameraSource(config)


class CameraSource:
    """Captures frames from a physical camera (native / picam / IMX500)."""

    def __init__(self, config: Config):
        self.logger = Logger("CameraSource")
        self.config = config
        self.camera_type: str = config.get('camera.model', 'native')
        self.camera = None
        self._running = False

        # IMX500 specific
        self._imx500 = None
        self._last_detections: Optional[dict] = None

    def start(self) -> bool:
        """Open the camera device."""
        try:
            if self.camera_type == 'imx500':
                return self._start_imx500()
            elif self.camera_type == 'picam':
                return self._start_picamera()
            else:
                return self._start_native()
        except Exception as e:
            self.logger.error(f"Camera start failed: {e}")
            return False

    def _start_native(self) -> bool:
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

    def _start_picamera(self) -> bool:
        if not _HAS_PICAMERA2:
            raise ImportError(
                f"picamera2 not available: {_PICAMERA2_IMPORT_ERROR}"
            )
        self.camera = Picamera2()
        res = self.config.get('camera.resolution', {})
        cam_config = self.camera.create_preview_configuration(
            main={"size": (res.get('width', 640), res.get('height', 640))},
            controls={"FrameRate": self.config.get_int('camera.fps', 30)},
        )
        self.camera.configure(cam_config)
        self.camera.start()
        self._running = True
        self.logger.info("Camera started (picamera)")
        return True

    def _start_imx500(self) -> bool:
        if not _HAS_PICAMERA2:
            raise ImportError(
                f"picamera2 not available: {_PICAMERA2_IMPORT_ERROR}"
            )
        model_path = self.config.get('camera.imx500.model_path', '')
        if not model_path or not Path(model_path).exists():
            raise FileNotFoundError(f"IMX500 model not found: {model_path}")

        self._imx500 = IMX500(model_path)
        intrinsics = self._imx500.network_intrinsics
        if intrinsics is None:
            intrinsics = NetworkIntrinsics()
            intrinsics.task = "object detection"

        confidence = self.config.get_float('camera.imx500.confidence', 0.5)
        if hasattr(intrinsics, 'threshold'):
            intrinsics.threshold = confidence
        if hasattr(intrinsics, 'iou_threshold'):
            intrinsics.iou_threshold = self.config.get_float('camera.imx500.iou_threshold', 0.5)
        if hasattr(intrinsics, 'max_detections'):
            intrinsics.max_detections = self.config.get_int('camera.imx500.max_detections', 10)

        self.camera = Picamera2(self._imx500.camera_num)
        res = self.config.get('camera.resolution', {})
        cam_config = self.camera.create_preview_configuration(
            main={"size": (res.get('width', 640), res.get('height', 640))},
            controls={"FrameRate": self.config.get_int('camera.fps', 30)},
        )
        self.camera.configure(cam_config)
        self._imx500.show_network_fw_progress_bar()
        self.camera.start(cam_config)
        self._running = True
        self.logger.info(f"Camera started (IMX500, confidence={confidence})")
        return True

    def read_frame(self) -> Optional[MatLike]:
        """Read a single frame. Returns None on failure."""
        if not self._running or self.camera is None:
            return None
        try:
            if self.camera_type == 'imx500':
                return self._read_imx500()
            elif self.camera_type == 'picam':
                return self._read_picam()
            else:
                ret, frame = self.camera.read()
                return frame if ret else None
        except Exception as e:
            self.logger.error(f"Frame read failed: {e}")
            return None

    def _read_picam(self) -> Optional[MatLike]:
        try:
            frame = self.camera.capture_array()
            # picamera2 returns RGB — convert to BGR for OpenCV consistency
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            return frame
        except Exception:
            return None

    def _read_imx500(self) -> Optional[MatLike]:
        try:
            request = self.camera.capture_request()
            frame = request.make_array("main")
            metadata = request.get_metadata()
            request.release()

            if frame.ndim == 3 and frame.shape[2] == 4:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

            np_outputs = self._imx500.get_outputs(metadata)
            if np_outputs is not None and len(np_outputs) >= 3:
                boxes, scores, classes = np_outputs[0], np_outputs[1], np_outputs[2]
                self._last_detections = {
                    "boxes": boxes,
                    "scores": scores,
                    "class_ids": classes.astype(int) if classes is not None else np.array([]),
                }
            else:
                self._last_detections = None
            return frame
        except Exception as e:
            self.logger.debug(f"IMX500 read failed: {e}")
            self._last_detections = None
            return None

    def get_imx500_detections(self) -> Optional[dict]:
        if self.camera_type != 'imx500':
            return None
        return self._last_detections

    def stop(self):
        """Release the camera."""
        self._running = False
        if self.camera is None:
            return
        try:
            if self.camera_type in ('imx500', 'picam'):
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

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_imx500(self) -> bool:
        return self.camera_type == 'imx500'


class VideoSource:
    """Reads frames from a video file on disk."""

    def __init__(self, config: Config, video_path: str):
        self.logger = Logger("VideoSource")
        self.config = config
        self.video_path = str(video_path)
        self.loop: bool = config.get_bool('camera.loop_video', True)
        self.cap: Optional[cv2.VideoCapture] = None
        self._running = False

    def start(self) -> bool:
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
        if not self._running or self.cap is None:
            return None
        ret, frame = self.cap.read()
        if not ret:
            if self.loop:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = self.cap.read()
                if ret:
                    return frame
            self._running = False
            return None
        return frame

    def stop(self):
        self._running = False
        if self.cap is not None:
            self.cap.release()
            self.cap = None
            self.logger.info("Video released")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_imx500(self) -> bool:
        return False

    def get_imx500_detections(self) -> Optional[dict]:
        return None
