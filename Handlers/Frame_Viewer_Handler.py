"""Frame Viewer Handler — a secondary Qt window that shows live camera / AI frames.

Polls a bounded Queue at ~30 fps and converts OpenCV BGR frames into QPixmaps.
Designed to coexist with the main DisplayHandler inside the same QApplication.

Enable with ``--show-frames`` CLI flag.
"""
import numpy as np
from queue import Queue, Empty

from PyQt6.QtWidgets import QMainWindow, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap

from utils.logger import Logger


class FrameViewerHandler(QMainWindow):
    """Live frame viewer window.

    Reads frames (numpy BGR arrays) from *viewer_queue* and displays them
    inside a QLabel, scaled to fit while preserving aspect ratio.

    The window should be created **after** the QApplication already exists
    (i.e. after ``DisplayHandler.__init__``).
    """

    def __init__(self, viewer_queue: Queue, title: str = "Safespace | Frame Viewer"):
        super().__init__()
        self.viewer_queue = viewer_queue
        self.logger = Logger("FrameViewer")

        # ── Window chrome ────────────────────────────────────────────
        self.setWindowTitle(title)
        self.setMinimumSize(640, 480)
        self.resize(960, 540)

        # ── Central image label ──────────────────────────────────────
        self.image_label = QLabel("Waiting for frames …")
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setStyleSheet("background: #111; color: #888; font-size: 16px;")

        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.image_label)
        self.setCentralWidget(central)

        # ── Poll timer (~30 fps) ─────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll_queue)
        self._timer.start(33)  # ~30 Hz

        self.logger.info("Frame viewer window created")

    # ── Internal ─────────────────────────────────────────────────────

    def _poll_queue(self) -> None:
        """Drain the queue and display only the latest frame."""
        latest: np.ndarray | None = None
        while True:
            try:
                latest = self.viewer_queue.get_nowait()
            except Empty:
                break

        if latest is not None:
            self._display_frame(latest)

    def _display_frame(self, frame: np.ndarray) -> None:
        """Convert a BGR numpy frame to QPixmap and set it on the label."""
        if frame.ndim == 2:
            # Grayscale
            h, w = frame.shape
            bytes_per_line = w
            q_img = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_Grayscale8)
        else:
            h, w, ch = frame.shape
            # OpenCV uses BGR — Qt needs RGB
            rgb = frame[..., ::-1].copy()  # fast BGR→RGB via numpy slice
            bytes_per_line = ch * w
            q_img = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)

        pixmap = QPixmap.fromImage(q_img)

        # Scale to label size, preserving aspect ratio
        scaled = pixmap.scaled(
            self.image_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)

    # ── Lifecycle ────────────────────────────────────────────────────

    def stop(self) -> None:
        """Stop the polling timer and close the window."""
        self._timer.stop()
        self.close()
