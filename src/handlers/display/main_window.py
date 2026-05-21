"""
Main Window — full Safespace dashboard layout with dev / prod modes.

Dev mode:   video feeds (input + AI) with FPS, lanes, speed, system monitor
Prod mode:  lanes, speed, accident warning banner
"""
from typing import Optional, Callable, List, Any

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette, QKeyEvent

from utils.config import Config
from utils.logger import Logger

from handlers.display.lane_widget import LaneWidget
from handlers.display.speed_widget import SpeedWidget
from handlers.display.video_feed_widget import VideoFeedWidget
from handlers.display.system_monitor_widget import SystemMonitorWidget


class MainWindow(QMainWindow):
    """Main Safespace dashboard window — supports dev and prod modes."""

    # ── Thread-safe signals ───────────────────────────────────────
    update_lane_signal = pyqtSignal(int, str)        # lane_index, status
    update_speed_signal = pyqtSignal(int)             # speed_limit
    set_accident_signal = pyqtSignal(bool)            # active
    reset_display_signal = pyqtSignal()               # no args
    push_input_frame_signal = pyqtSignal(object)      # numpy BGR frame
    push_ai_frame_signal = pyqtSignal(object)         # numpy BGR frame (annotated)
    update_gps_signal = pyqtSignal(bool)              # fix status

    def __init__(self, config: Config, on_manual_trigger: Optional[Callable] = None):
        super().__init__()
        self.config = config
        self.on_manual_trigger = on_manual_trigger
        self.logger = Logger("Display")

        self._mode = config.get('display.mode', 'prod').lower()
        num_lanes = config.get_int('node.lanes', 3)
        default_speed = config.get_int('node.default_speed', 120)
        win_width = config.get_int('display.width', 1500)
        win_height = config.get_int('display.height', 856)

        # ── Window setup ──
        title_suffix = " [DEV]" if self._mode == "dev" else ""
        self.setWindowTitle(f"Safespace — Highway Monitor{title_suffix}")
        self.resize(win_width, win_height)
        self.setMinimumSize(960, 540)

        # Dark palette
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1a1a2e"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Dev-only widgets (set to None so prod code can safely ignore)
        self.input_feed: Optional[VideoFeedWidget] = None
        self.ai_feed: Optional[VideoFeedWidget] = None
        self.system_monitor: Optional[SystemMonitorWidget] = None

        # ── Build UI based on mode ──
        if self._mode == "dev":
            self._build_dev_ui(num_lanes, default_speed)
        else:
            self._build_prod_ui(num_lanes, default_speed)

        # ── Connect signals → slots ──
        self.update_lane_signal.connect(self._update_lane)
        self.update_speed_signal.connect(self._update_speed)
        self.set_accident_signal.connect(self._set_accident)
        self.reset_display_signal.connect(self._reset_display)
        self.push_input_frame_signal.connect(self._push_input_frame)
        self.push_ai_frame_signal.connect(self._push_ai_frame)
        self.update_gps_signal.connect(self._update_gps_indicator)

        # Accident flash timer
        self._flash_timer = QTimer(self)
        self._flash_timer.timeout.connect(self._flash_toggle)
        self._flash_visible = True
        self._default_speed = default_speed

        self.logger.info(f"Display initialized — mode={self._mode}, {num_lanes} lanes, speed={default_speed}")

    # ── Dev Layout ────────────────────────────────────────────────

    def _build_dev_ui(self, num_lanes: int, default_speed: int):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 15, 20, 15)
        root.setSpacing(12)

        # Header
        header = QLabel("SAFESPACE HIGHWAY MONITOR  [DEV]")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.setStyleSheet("color: #00d4ff; letter-spacing: 3px; background: transparent;")
        root.addWidget(header)

        # Accident banner (hidden)
        self.accident_banner = QLabel("⚠  ACCIDENT DETECTED  ⚠")
        self.accident_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.accident_banner.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.accident_banner.setStyleSheet("""
            background: rgba(255, 50, 50, 0.25);
            color: #ff4444;
            border: 2px solid #ff4444;
            border-radius: 10px;
            padding: 10px;
        """)
        self.accident_banner.setVisible(False)
        root.addWidget(self.accident_banner)

        # Middle: feeds (left) + lanes/speed/monitor (right)
        middle = QHBoxLayout()
        middle.setSpacing(15)

        # Left column: video feeds stacked vertically
        feeds_col = QVBoxLayout()
        feeds_col.setSpacing(10)

        self.input_feed = VideoFeedWidget("INPUT FEED")
        feeds_col.addWidget(self.input_feed, stretch=1)

        self.ai_feed = VideoFeedWidget("AI FEED")
        feeds_col.addWidget(self.ai_feed, stretch=1)

        middle.addLayout(feeds_col, stretch=3)

        # Right column: lanes + speed + system monitor
        right_col = QVBoxLayout()
        right_col.setSpacing(12)

        # Lanes
        lanes_frame = QFrame()
        lanes_layout = QHBoxLayout(lanes_frame)
        lanes_layout.setSpacing(10)
        self.lane_widgets: List[LaneWidget] = []
        for i in range(num_lanes):
            lane = LaneWidget(i)
            self.lane_widgets.append(lane)
            lanes_layout.addWidget(lane)
        right_col.addWidget(lanes_frame, stretch=1)

        # Speed + System monitor side by side
        bottom_right = QHBoxLayout()
        bottom_right.setSpacing(12)

        self.speed_widget = SpeedWidget(default_speed)
        bottom_right.addWidget(self.speed_widget, alignment=Qt.AlignmentFlag.AlignCenter)

        self.system_monitor = SystemMonitorWidget()
        bottom_right.addWidget(self.system_monitor, alignment=Qt.AlignmentFlag.AlignCenter)

        right_col.addLayout(bottom_right)

        middle.addLayout(right_col, stretch=2)
        root.addLayout(middle, stretch=1)

        # Status bar
        self._add_status_bar(root)

    # ── Prod Layout ───────────────────────────────────────────────

    def _build_prod_ui(self, num_lanes: int, default_speed: int):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(30, 20, 30, 20)
        root.setSpacing(20)

        # Header
        header = QLabel("SAFESPACE HIGHWAY MONITOR")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        header.setStyleSheet("color: #00d4ff; letter-spacing: 3px; background: transparent;")
        root.addWidget(header)

        # Accident banner (hidden)
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
        root.addWidget(self.accident_banner)

        # Middle: lanes + speed
        middle = QHBoxLayout()
        middle.setSpacing(20)

        # Lanes
        lanes_frame = QFrame()
        lanes_layout = QHBoxLayout(lanes_frame)
        lanes_layout.setSpacing(15)
        self.lane_widgets: List[LaneWidget] = []
        for i in range(num_lanes):
            lane = LaneWidget(i)
            self.lane_widgets.append(lane)
            lanes_layout.addWidget(lane)
        middle.addWidget(lanes_frame, stretch=3)

        # Speed
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.speed_widget = SpeedWidget(default_speed)
        right.addWidget(self.speed_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        middle.addLayout(right, stretch=1)

        root.addLayout(middle, stretch=1)

        # Status bar
        self._add_status_bar(root)

    # ── Shared helpers ────────────────────────────────────────────

    def _add_status_bar(self, root: QVBoxLayout):
        node_id = self.config.get('node.id', '?')
        desc = self.config.get('node.description', '')
        mode_tag = f"  •  Mode: {self._mode.upper()}"
        status = QLabel(f"Node {node_id}  •  {desc}{mode_tag}  •  Press SPACE to report manually")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setFont(QFont("Segoe UI", 9))
        status.setStyleSheet("color: #555555; background: transparent;")
        root.addWidget(status)
        # GPS indicator
        self.gps_label = QLabel("●  GPS: Searching...")
        self.gps_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.gps_label.setFont(QFont("Segoe UI", 9))
        self.gps_label.setStyleSheet("color: #ff9900; background: transparent;")
        root.addWidget(self.gps_label)

    # ── Thread-safe public API ────────────────────────────────────

    def update_lane(self, lane_index: int, status: str):
        self.update_lane_signal.emit(lane_index, status)

    def update_speed(self, limit: int):
        self.update_speed_signal.emit(limit)

    def set_accident_alert(self, active: bool):
        self.set_accident_signal.emit(active)

    def reset_display(self):
        self.reset_display_signal.emit()

    def push_input_frame(self, frame):
        self.push_input_frame_signal.emit(frame)

    def push_ai_frame(self, frame):
        self.push_ai_frame_signal.emit(frame)

    def update_gps_status(self, has_fix: bool):
        """Called from outside Qt thread to update GPS indicator."""
        self.update_gps_signal.emit(has_fix)

    # ── Slots (run on Qt main thread) ─────────────────────────────

    def _update_lane(self, lane_index: int, status: str):
        if 0 <= lane_index < len(self.lane_widgets):
            self.lane_widgets[lane_index].set_status(status)

    def _update_speed(self, limit: int):
        self.speed_widget.set_speed(limit)

    def _set_accident(self, active: bool):
        self.accident_banner.setVisible(active)
        self.speed_widget.set_alert_mode(active)
        if active:
            self._flash_timer.start(500)
        else:
            self._flash_timer.stop()
            self.accident_banner.setVisible(False)

    def _push_input_frame(self, frame):
        if self.input_feed is not None:
            self.input_feed.push_frame(frame)

    def _push_ai_frame(self, frame):
        if self.ai_feed is not None:
            self.ai_feed.push_frame(frame)

    def _reset_display(self):
        for lane in self.lane_widgets:
            lane.set_status("up")
        self.speed_widget.set_speed(self._default_speed)
        self.speed_widget.set_alert_mode(False)
        self.accident_banner.setVisible(False)
        self._flash_timer.stop()

    def _flash_toggle(self):
        self._flash_visible = not self._flash_visible
        self.accident_banner.setVisible(self._flash_visible)

    def _update_gps_indicator(self, has_fix: bool):
        if has_fix:
            self.gps_label.setText("●  GPS: Fix Acquired")
            self.gps_label.setStyleSheet("color: #00ff88; background: transparent;")
        else:
            self.gps_label.setText("●  GPS: Searching...")
            self.gps_label.setStyleSheet("color: #ff9900; background: transparent;")

    # ── Keyboard ──────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and self.on_manual_trigger:
            self.on_manual_trigger()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)
