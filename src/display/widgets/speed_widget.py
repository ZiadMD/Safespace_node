"""
Speed Widget — circular speed limit display.
"""
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class SpeedWidget(QFrame):
    """Speed limit display with normal / alert modes."""

    def __init__(self, default_speed: int = 120, parent=None):
        super().__init__(parent)
        self.setObjectName("speed_widget")
        self.setFixedSize(180, 220)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        # Title
        self.title_label = QLabel("SPEED LIMIT")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.title_label.setStyleSheet("color: #aaaaaa; background: transparent;")
        layout.addWidget(self.title_label)

        # Speed number
        self.speed_label = QLabel(str(default_speed))
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_label.setFont(QFont("Segoe UI", 42, QFont.Weight.Bold))
        self.speed_label.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(self.speed_label)

        # Unit
        self.unit_label = QLabel("km/h")
        self.unit_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unit_label.setFont(QFont("Segoe UI", 11))
        self.unit_label.setStyleSheet("color: #888888; background: transparent;")
        layout.addWidget(self.unit_label)

        self._set_normal_style()

    def set_speed(self, limit: int):
        """Update the displayed speed limit."""
        self.speed_label.setText(str(limit))

    def set_alert_mode(self, active: bool):
        """Switch between normal and alert styling."""
        if active:
            self.setStyleSheet("""
                QFrame#speed_widget {
                    background: rgba(255, 50, 50, 0.15);
                    border: 3px solid rgba(255, 50, 50, 0.7);
                    border-radius: 16px;
                }
            """)
            self.speed_label.setStyleSheet("color: #ff4444; background: transparent;")
        else:
            self._set_normal_style()
            self.speed_label.setStyleSheet("color: #ffffff; background: transparent;")

        # Re-apply child styles so they don't get overridden
        self.title_label.setStyleSheet("color: #aaaaaa; background: transparent;")
        self.unit_label.setStyleSheet("color: #888888; background: transparent;")

    def _set_normal_style(self):
        self.setStyleSheet("""
            QFrame#speed_widget {
                background: rgba(255, 255, 255, 0.06);
                border: 2px solid rgba(255, 255, 255, 0.15);
                border-radius: 16px;
            }
        """)
