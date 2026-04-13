"""
Video Feed Widget — renders frames with FPS counter.

In v2, this widget doesn't receive frames via signals.
Instead, the parent app.py calls `render_frame(numpy_array)` on a timer.
"""
import time
from collections import deque

import cv2
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QSizePolicy
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QImage, QPixmap


class VideoFeedWidget(QFrame):
    """Displays a live video stream with a title and real-time FPS counter."""

    def __init__(self, title: str = "FEED", parent=None):
        super().__init__(parent)
        self.setObjectName(f"feed_{title.lower().replace(' ', '_')}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 240)

        self.setStyleSheet(f"""
            QFrame#{self.objectName()} {{
                background: rgba(0, 0, 0, 0.4);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Title
        self._title_label = QLabel(title)
        self._title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._title_label.setStyleSheet("color: #888; background: transparent;")
        self._title_label.setFixedHeight(20)
        layout.addWidget(self._title_label)

        # Video frame display
        self._frame_label = QLabel()
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._frame_label.setStyleSheet("background: transparent;")
        self._frame_label.setMinimumSize(300, 200)
        layout.addWidget(self._frame_label, stretch=1)

        # FPS overlay label
        self._fps_label = QLabel("0 FPS")
        self._fps_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._fps_label.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self._fps_label.setStyleSheet("color: #00d4ff; background: transparent;")
        self._fps_label.setFixedHeight(16)
        layout.addWidget(self._fps_label)

        # FPS tracking
        self._timestamps: deque = deque(maxlen=60)

    def render_frame(self, frame):
        """
        Render a BGR numpy frame and update FPS counter.

        Called from the parent's QTimer — NOT via signals.
        """
        if frame is None:
            return

        now = time.monotonic()
        self._timestamps.append(now)
        self._update_fps()

        try:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb.shape
            qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
            pixmap = QPixmap.fromImage(qimg)

            scaled = pixmap.scaled(
                self._frame_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.FastTransformation,
            )
            self._frame_label.setPixmap(scaled)
        except Exception:
            pass

    def _update_fps(self):
        if len(self._timestamps) < 2:
            return
        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed > 0:
            fps = (len(self._timestamps) - 1) / elapsed
            self._fps_label.setText(f"{fps:.1f} FPS")
