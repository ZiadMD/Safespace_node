"""
Display Handler - PyQt6 GUI dashboard for Safespace highway status.

Shows:
  - Dynamic lane indicators (SVG icons) — number of lanes from config
  - Speed limit display — updates on server instruction
  - Accident alert banner — flashes when accident detected
  - Accident image — shows the detection frame

All updates are thread-safe via Qt signals so any thread can call the public API.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional, Callable, List
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QSizePolicy, QGraphicsDropShadowEffect
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QPixmap, QFont, QColor, QPalette, QKeyEvent
from PyQt6.QtSvgWidgets import QSvgWidget

from utils.config import Config
from utils.logger import Logger
from utils.constants import ROAD_SIGNS_DIR, ACCIDENT_IMAGES_DIR


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


# ═══════════════════════════════════════════════════════════════════
#  LaneWidget — A single lane indicator
# ═══════════════════════════════════════════════════════════════════

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


# ═══════════════════════════════════════════════════════════════════
#  SpeedWidget — Speed limit display (circle)
# ═══════════════════════════════════════════════════════════════════

class SpeedWidget(QFrame):
    """Circular speed limit display."""

    def __init__(self, default_speed: int = 120, parent=None):
        super().__init__(parent)
        self.setFixedSize(180, 220) # Size of the circular speed display size: width, height 

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(4)

        # Title
        title = QLabel("SPEED LIMIT")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        title.setStyleSheet("color: #aaaaaa; background: transparent;")
        layout.addWidget(title)

        # Speed number
        self.speed_label = QLabel(str(default_speed))
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_label.setFont(QFont("Segoe UI", 42, QFont.Weight.Bold))
        self.speed_label.setStyleSheet("color: #ffffff; background: transparent;")
        layout.addWidget(self.speed_label)

        # Unit
        unit = QLabel("km/h")
        unit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        unit.setFont(QFont("Segoe UI", 11))
        unit.setStyleSheet("color: #888888; background: transparent;")
        layout.addWidget(unit)

        self._set_normal_style()

    def set_speed(self, limit: int):
        """Update the displayed speed limit."""
        self.speed_label.setText(str(limit))

    def set_alert_mode(self, active: bool):
        """Switch between normal and alert styling."""
        if active:
            self.setStyleSheet("""
                SpeedWidget {
                    background: rgba(255, 50, 50, 0.15);
                    border: 3px solid rgba(255, 50, 50, 0.7);
                    border-radius: 16px;
                }
            """)
            self.speed_label.setStyleSheet("color: #ff4444; background: transparent;")
        else:
            self._set_normal_style()
            self.speed_label.setStyleSheet("color: #ffffff; background: transparent;")

    def _set_normal_style(self):
        self.setStyleSheet("""
            SpeedWidget {
                background: rgba(255, 255, 255, 0.06);
                border: 2px solid rgba(255, 255, 255, 0.15);
                border-radius: 16px;
            }
        """)


# ═══════════════════════════════════════════════════════════════════
#  MainWindow — Full dashboard window
# ═══════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Main Safespace dashboard window."""

    # Thread-safe signals
    update_lane_signal = pyqtSignal(int, str)       # lane_index, status
    update_speed_signal = pyqtSignal(int)            # speed_limit
    set_accident_signal = pyqtSignal(bool)           # active
    show_accident_image_signal = pyqtSignal(object)  # QPixmap or numpy array
    reset_display_signal = pyqtSignal()              # no args

    def __init__(self, config: Config, on_manual_trigger: Optional[Callable] = None):
        super().__init__()
        self.config = config
        self.on_manual_trigger = on_manual_trigger
        self.logger = Logger("Display")

        num_lanes = self.config.get_int('node.lanes', 3)
        default_speed = self.config.get_int('node.default_speed', 120)
        win_width = self.config.get_int('display.width', 1500)
        win_height = self.config.get_int('display.height', 856)

        # ── Window setup ──
        self.setWindowTitle("Safespace — Highway Monitor")
        self.resize(win_width, win_height)
        self.setMinimumSize(960, 540)

        # Dark palette
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1a1a2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # ── Central widget ──
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(30, 20, 30, 20)
        root_layout.setSpacing(20)

        # ── Header ──
        header = QLabel("SAFESPACE HIGHWAY MONITOR")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        header.setStyleSheet("color: #00d4ff; letter-spacing: 3px; background: transparent;")
        root_layout.addWidget(header)

        # ── Accident banner (hidden by default) ──
        self.accident_banner = QLabel("⚠  ACCIDENT DETECTED  ⚠")
        self.accident_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.accident_banner.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.accident_banner.setStyleSheet("""
            background: rgba(255, 50, 50, 0.25);
            color: #ff4444;
            border: 2px solid #ff4444;
            border-radius: 10px;
            padding: 12px;
        """)
        self.accident_banner.setVisible(False)
        root_layout.addWidget(self.accident_banner)

        # ── Middle section: Lanes + Speed + Image ──
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(20)

        # Lanes section
        lanes_frame = QFrame()
        lanes_layout = QHBoxLayout(lanes_frame)
        lanes_layout.setSpacing(15)
        self.lane_widgets: List[LaneWidget] = []
        for i in range(num_lanes):
            lane = LaneWidget(i)
            self.lane_widgets.append(lane)
            lanes_layout.addWidget(lane)
        middle_layout.addWidget(lanes_frame, stretch=3)

        # Right panel: speed + accident image
        right_panel = QVBoxLayout()
        right_panel.setSpacing(15)
        right_panel.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.speed_widget = SpeedWidget(default_speed)
        right_panel.addWidget(self.speed_widget, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Accident image placeholder
        self.accident_image_label = QLabel()
        self.accident_image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.accident_image_label.setMinimumSize(260, 180)
        self.accident_image_label.setMaximumSize(400, 300)
        self.accident_image_label.setStyleSheet("""
            background: rgba(255, 255, 255, 0.04);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 10px;
            color: #555;
        """)
        self.accident_image_label.setText("No incident image")
        self.accident_image_label.setFont(QFont("Segoe UI", 10))
        right_panel.addWidget(self.accident_image_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        middle_layout.addLayout(right_panel, stretch=1)
        root_layout.addLayout(middle_layout, stretch=1)

        # ── Status bar ──
        node_id = self.config.get('node.id', '?')
        desc = self.config.get('node.description', '')
        self.status_label = QLabel(f"Node {node_id}  •  {desc}  •  Press SPACE to report manually")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setFont(QFont("Segoe UI", 9))
        self.status_label.setStyleSheet("color: #555555; background: transparent;")
        root_layout.addWidget(self.status_label)

        # ── Connect signals to slots ──
        self.update_lane_signal.connect(self._update_lane)
        self.update_speed_signal.connect(self._update_speed)
        self.set_accident_signal.connect(self._set_accident)
        self.show_accident_image_signal.connect(self._show_accident_image)
        self.reset_display_signal.connect(self._reset_display)

        # Accident flash timer
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_toggle)
        self._flash_visible = True

        self._default_speed = default_speed
        self.logger.info(f"Display initialized ({num_lanes} lanes, speed={default_speed})")

    # ── Thread-safe public API (can be called from any thread) ────

    def update_lane(self, lane_index: int, status: str):
        """Thread-safe: update a lane's status."""
        self.update_lane_signal.emit(lane_index, status)

    def update_speed(self, limit: int):
        """Thread-safe: update the speed limit."""
        self.update_speed_signal.emit(limit)

    def set_accident_alert(self, active: bool):
        """Thread-safe: show or hide the accident banner."""
        self.set_accident_signal.emit(active)

    def show_accident_image(self, image):
        """Thread-safe: display an accident image (numpy BGR array or QPixmap)."""
        self.show_accident_image_signal.emit(image)

    def reset_display(self):
        """Thread-safe: reset all UI to default state."""
        self.reset_display_signal.emit()

    # ── Slot implementations (run on Qt main thread) ──────────────

    def _update_lane(self, lane_index: int, status: str):
        if 0 <= lane_index < len(self.lane_widgets):
            self.lane_widgets[lane_index].set_status(status)

    def _update_speed(self, limit: int):
        self.speed_widget.set_speed(limit)

    def _set_accident(self, active: bool):
        self.accident_banner.setVisible(active)
        self.speed_widget.set_alert_mode(active)
        if active:
            self._flash_timer.start(500)  # flash every 500ms
        else:
            self._flash_timer.stop()
            self.accident_banner.setVisible(False)

    def _show_accident_image(self, image):
        """Display an image in the accident panel. Accepts numpy BGR array or QPixmap."""
        try:
            if isinstance(image, QPixmap):
                pixmap = image
            else:
                # Assume numpy BGR array
                import cv2
                import numpy as np
                rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
                from PyQt6.QtGui import QImage
                h, w, ch = rgb.shape
                bytes_per_line = ch * w
                qimg = QImage(rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(qimg)

            scaled = pixmap.scaled(
                self.accident_image_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.accident_image_label.setPixmap(scaled)
            self.accident_image_label.setText("")
        except Exception as e:
            self.logger.error(f"Failed to show accident image: {e}")

    def _reset_display(self):
        """Reset everything to default normal state."""
        for lane in self.lane_widgets:
            lane.set_status("up")
        self.speed_widget.set_speed(self._default_speed)
        self.speed_widget.set_alert_mode(False)
        self.accident_banner.setVisible(False)
        self._flash_timer.stop()
        self.accident_image_label.clear()
        self.accident_image_label.setText("No incident image")

    def _flash_toggle(self):
        """Toggle accident banner visibility for flashing effect."""
        self._flash_visible = not self._flash_visible
        self.accident_banner.setVisible(self._flash_visible)

    # ── Keyboard ──────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and self.on_manual_trigger:
            self.on_manual_trigger()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)


# ═══════════════════════════════════════════════════════════════════
#  DisplayHandler — Public interface (wraps QApplication + MainWindow)
# ═══════════════════════════════════════════════════════════════════

class DisplayHandler:
    """
    Display Handler — creates and manages the PyQt6 dashboard.
    
    Usage:
        display = DisplayHandler(config, on_manual_trigger=my_callback)
        # From other threads:
        display.update_lane_status(0, "blocked")
        display.update_speed_limit(60)
        display.set_accident_alert(True)
        display.show_accident_image(frame)
        # Blocks:
        display.start()
    """

    def __init__(self, config: Config, on_manual_trigger: Optional[Callable] = None):
        self.config = config
        self.on_manual_trigger = on_manual_trigger
        self.logger = Logger("DisplayHandler")

        self._app: Optional[QApplication] = None
        self._window: Optional[MainWindow] = None

    def start(self):
        """
        Start the Qt event loop. This BLOCKS until the window is closed.
        Call this from the main thread.
        """
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._window = MainWindow(self.config, on_manual_trigger=self.on_manual_trigger)

        fullscreen = self.config.get_bool('display.fullscreen', False)
        if fullscreen:
            self._window.showFullScreen()
        else:
            self._window.show()

        self.logger.info("Display started")
        self._app.exec()

    # ── Thread-safe API (delegates to window signals) ─────────────

    def update_lane_status(self, lane_index: int, status: str):
        """Update a specific lane's icon and label."""
        if self._window:
            self._window.update_lane(lane_index, status)

    def update_speed_limit(self, limit: int):
        """Update the speed limit display."""
        if self._window:
            self._window.update_speed(limit)

    def set_accident_alert(self, active: bool):
        """Show or hide the flashing accident banner."""
        if self._window:
            self._window.set_accident_alert(active)

    def show_accident_image(self, image):
        """Display an accident image (numpy BGR frame or QPixmap)."""
        if self._window:
            self._window.show_accident_image(image)

    def reset_display(self):
        """Reset all UI elements to default state."""
        if self._window:
            self._window.reset_display()


if __name__ == "__main__":
    def on_space():
        print("SPACE pressed — manual report!")

    config = Config()
    display = DisplayHandler(config, on_manual_trigger=on_space)

    # Simulate updates after 2 seconds
    import threading

    def simulate():
        import time
        time.sleep(2)
        display.update_lane_status(0, "blocked")
        display.update_lane_status(1, "right")
        display.update_speed_limit(60)
        display.set_accident_alert(True)
        display.show_accident_image(QPixmap(str(ACCIDENT_IMAGES_DIR / "image.png")))
        time.sleep(5)
        display.reset_display()

    threading.Thread(target=simulate, daemon=True).start()
    display.start()
