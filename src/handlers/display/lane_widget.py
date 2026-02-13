"""
Lane Widget — single lane indicator with SVG icon and status label.
"""
from pathlib import Path

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont
from PyQt6.QtSvgWidgets import QSvgWidget

from utils.constants import ROAD_SIGNS_DIR


# ── Lane Status → Visual Mapping ─────────────────────────────────

LANE_VISUALS = {
    "up": {
        "icon": "go_straight.svg",
        "bg": "rgba(0, 255, 136, 0.12)",
        "border": "rgba(0, 255, 136, 0.6)",
        "label": "OPEN",
        "label_color": "#00ff88",
    },
    "blocked": {
        "icon": "blocked.svg",
        "bg": "rgba(255, 50, 50, 0.12)",
        "border": "rgba(255, 50, 50, 0.6)",
        "label": "BLOCKED",
        "label_color": "#ff3232",
    },
    "left": {
        "icon": "turn-left.svg",
        "bg": "rgba(255, 165, 0, 0.12)",
        "border": "rgba(255, 165, 0, 0.6)",
        "label": "TURN LEFT",
        "label_color": "#ffa500",
    },
    "right": {
        "icon": "turn-right.svg",
        "bg": "rgba(255, 165, 0, 0.12)",
        "border": "rgba(255, 165, 0, 0.6)",
        "label": "TURN RIGHT",
        "label_color": "#ffa500",
    },
}


class LaneWidget(QFrame):
    """Visual widget for a single lane: large SVG icon + small status label."""

    def __init__(self, lane_number: int, parent=None):
        super().__init__(parent)
        self.lane_number = lane_number
        self.setObjectName(f"lane_{lane_number}")

        self.setMinimumSize(160, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(6)
        layout.setContentsMargins(10, 14, 10, 14)

        # Lane number label (small, top)
        self.title_label = QLabel(f"LANE {lane_number + 1}")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #888888; background: transparent;")
        layout.addWidget(self.title_label)

        # SVG Icon — large and dominant
        self.icon_widget = QSvgWidget()
        self.icon_widget.setFixedSize(QSize(160, 160))
        icon_container = QHBoxLayout()
        icon_container.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_container.addWidget(self.icon_widget)
        layout.addLayout(icon_container, stretch=1)

        # Status label (small subtitle below icon)
        self.status_label = QLabel("OPEN")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.status_label.setStyleSheet("color: #00ff88; background: transparent;")
        layout.addWidget(self.status_label)

        # Default state
        self.set_status("up")

    def set_status(self, status: str):
        """Update the lane to show the given status."""
        status = status.lower()
        visuals = LANE_VISUALS.get(status, LANE_VISUALS["up"])

        # Load SVG icon
        icon_path = str(ROAD_SIGNS_DIR / visuals["icon"])
        if Path(icon_path).exists():
            self.icon_widget.load(icon_path)

        # Update frame style — use #id selector so it does NOT cascade to children
        obj_id = self.objectName()
        self.setStyleSheet(f"""
            QFrame#{obj_id} {{
                background: {visuals['bg']};
                border: 2px solid {visuals['border']};
                border-radius: 16px;
            }}
        """)

        # Re-apply child styles explicitly (Qt cascading would otherwise blank them)
        self.title_label.setStyleSheet("color: #888888; background: transparent;")
        self.status_label.setText(visuals["label"])
        self.status_label.setStyleSheet(
            f"color: {visuals['label_color']}; background: transparent;"
        )
        self.icon_widget.setStyleSheet("background: transparent;")
