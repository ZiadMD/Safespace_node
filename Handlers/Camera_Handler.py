"""Camera Handler - Manages low-level frame capture using OpenCV.

Implements the FrameSource protocol. Frames are read via read_frame()
rather than pushed through callbacks — the CaptureStage pipeline stage
is responsible for pulling frames and putting them into the queue.
"""
import cv2
import numpy as np
import threading
import time
from typing import Optional
from utils.logger import Logger


class CameraHandler:
    """Handles interaction with the physical camera hardware.
    
    Implements the FrameSource protocol:
        start() -> bool
        read_frame() -> Optional[np.ndarray]
        stop() -> None
    """

    def __init__(self, config: dict):
        """
        Initialize the camera handler.

        Args:
            config: Camera-specific configuration subset
        """
        self.config = config
        self.logger = Logger("CameraHandler")
        self.cap: Optional[cv2.VideoCapture] = None
        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._latest_frame = None
        self._frame_lock = threading.Lock()
        self._ready = False

    # ── FrameSource protocol ──────────────────────────────────────────

    def start(self) -> bool:
        """Open the camera and begin the background capture thread."""
        if self._active:
            return True

        self._active = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

        # Wait briefly for hardware init
        deadline = time.monotonic() + 5.0
        while not self._ready and time.monotonic() < deadline:
            time.sleep(0.05)

        if not self._ready:
            self.logger.error("Camera failed to become ready within timeout")
            self._active = False
            return False

        self.logger.info("Camera started")
        return True

    def read_frame(self) -> Optional[np.ndarray]:
        """Return the most recently captured frame (thread-safe)."""
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def stop(self) -> None:
        """Cleanly stop the camera capture and release hardware."""
        self._active = False
        if self._thread:
            self._thread.join(timeout=2.0)
        self.logger.info("Camera stopped")

    # ── Internal ──────────────────────────────────────────────────────

    def _capture_loop(self) -> None:
        """Background thread: opens hardware, continuously grabs frames."""
        index = self.config.get('index', 0)
        width = self.config.get('width', 640)
        height = self.config.get('height', 480)

        self.logger.info(f"Initializing camera hardware (Index: {index})...")
        self.cap = cv2.VideoCapture(index)

        if not self.cap.isOpened():
            self.logger.error(f"Failed to open camera index {index}")
            self._active = False
            return

        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self._ready = True
        self.logger.info(f"Camera hardware ready at {width}x{height}")

        while self._active:
            ret, frame = self.cap.read()
            if not ret:
                self.logger.warning("Captured empty frame, retrying...")
                time.sleep(0.1)
                continue

            with self._frame_lock:
                self._latest_frame = frame

        # Cleanup
        if self.cap:
            self.cap.release()
            self.cap = None
        self._ready = False
