"""
System Monitor Widget — displays CPU usage with a progress bar and label.

Uses psutil to sample CPU % on a QTimer.
"""
import psutil
from PyQt6.QtWidgets import QFrame, QVBoxLayout, QLabel, QProgressBar
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont


class SystemMonitorWidget(QFrame):
    """Compact CPU / system usage monitor for the dev dashboard."""

    def __init__(self, interval_ms: int = 1000, parent=None):
        super().__init__(parent)
        self.setObjectName("system_monitor")
        self.setFixedSize(200, 120)

        self.setStyleSheet("""
            QFrame#system_monitor {
                background: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Title
        title = QLabel("SYSTEM")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        title.setStyleSheet("color: #888; background: transparent;")
        layout.addWidget(title)

        # CPU label
        self._cpu_label = QLabel("CPU: 0%")
        self._cpu_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._cpu_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self._cpu_label.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(self._cpu_label)

        # CPU progress bar
        self._cpu_bar = QProgressBar()
        self._cpu_bar.setRange(0, 100)
        self._cpu_bar.setValue(0)
        self._cpu_bar.setTextVisible(False)
        self._cpu_bar.setFixedHeight(10)
        self._cpu_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 5px;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #00d4ff, stop:1 #00ff88);
                border-radius: 5px;
            }
        """)
        layout.addWidget(self._cpu_bar)

        # Memory label
        self._mem_label = QLabel("MEM: 0%")
        self._mem_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mem_label.setFont(QFont("Segoe UI", 9))
        self._mem_label.setStyleSheet("color: #666; background: transparent;")
        layout.addWidget(self._mem_label)

        # Polling timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._sample)
        self._timer.start(interval_ms)

        # Stylesheet caching — only re-apply when the color tier changes
        self._last_bar_color = None

        # Initial sample
        self._sample()

    def _sample(self):
        """Read CPU and memory usage."""
        cpu = psutil.cpu_percent(interval=None)
        mem = psutil.virtual_memory().percent

        self._cpu_label.setText(f"CPU: {cpu:.0f}%")
        self._cpu_bar.setValue(int(cpu))
        self._mem_label.setText(f"MEM: {mem:.0f}%")

        # Color the bar based on load — only update stylesheet when tier changes
        if cpu > 80:
            chunk_color = "#ff4444"
        elif cpu > 50:
            chunk_color = "#ffa500"
        else:
            chunk_color = "#00ff88"

        if chunk_color != self._last_bar_color:
            self._last_bar_color = chunk_color
            self._cpu_bar.setStyleSheet(f"""
                QProgressBar {{
                    background: rgba(255, 255, 255, 0.08);
                    border: none;
                    border-radius: 5px;
                }}
                QProgressBar::chunk {{
                    background: {chunk_color};
                    border-radius: 5px;
                }}
            """)
