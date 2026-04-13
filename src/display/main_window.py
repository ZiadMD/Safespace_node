"""
Main Window — Safespace dashboard with dev / prod modes and a mode indicator.

In v2, the window does NOT receive frames via signals. Instead,
the parent DisplayApp calls pull methods on a QTimer.
"""
from typing import Optional, Callable, List

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QPalette, QKeyEvent

from core.config import Config
from core.logger import Logger
from core.constants import (
    THEME_BG, THEME_ACCENT, THEME_DANGER, THEME_MUTED, THEME_DIM,
)

from display.widgets.lane_widget import LaneWidget
from display.widgets.speed_widget import SpeedWidget
from display.widgets.video_feed import VideoFeedWidget
from display.widgets.system_monitor_widget import SystemMonitorWidget


class MainWindow(QMainWindow):
    """Main Safespace dashboard — supports dev and prod modes with mode indicator."""

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

        # Window setup
        title_suffix = " [DEV]" if self._mode == "dev" else ""
        self.setWindowTitle(f"Safespace — Highway Monitor{title_suffix}")
        self.resize(win_width, win_height)
        self.setMinimumSize(960, 540)

        # Dark palette
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(THEME_BG))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#ffffff"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

        # Dev-only widgets
        self.input_feed: Optional[VideoFeedWidget] = None
        self.ai_feed: Optional[VideoFeedWidget] = None
        self.system_monitor: Optional[SystemMonitorWidget] = None

        # Build UI
        if self._mode == "dev":
            self._build_dev_ui(num_lanes, default_speed)
        else:
            self._build_prod_ui(num_lanes, default_speed)

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

        # Header with mode badge
        header_row = QHBoxLayout()
        header = QLabel("SAFESPACE HIGHWAY MONITOR  [DEV]")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {THEME_ACCENT}; letter-spacing: 3px; background: transparent;")
        header_row.addWidget(header, stretch=1)

        # Mode indicator badge
        self.mode_badge = QLabel("NORMAL")
        self.mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.mode_badge.setFixedSize(100, 28)
        self._set_mode_badge_style("normal")
        header_row.addWidget(self.mode_badge)
        root.addLayout(header_row)

        # Accident banner (hidden)
        self.accident_banner = QLabel("⚠  ACCIDENT DETECTED  ⚠")
        self.accident_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.accident_banner.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        self.accident_banner.setStyleSheet(f"""
            background: rgba(255, 50, 50, 0.25);
            color: {THEME_DANGER};
            border: 2px solid {THEME_DANGER};
            border-radius: 10px;
            padding: 10px;
        """)
        self.accident_banner.setVisible(False)
        root.addWidget(self.accident_banner)

        # Middle: feeds (left) + lanes/speed/monitor (right)
        middle = QHBoxLayout()
        middle.setSpacing(15)

        # Left column: video feeds
        feeds_col = QVBoxLayout()
        feeds_col.setSpacing(10)
        self.input_feed = VideoFeedWidget("INPUT FEED")
        feeds_col.addWidget(self.input_feed, stretch=1)
        self.ai_feed = VideoFeedWidget("AI FEED")
        feeds_col.addWidget(self.ai_feed, stretch=1)
        middle.addLayout(feeds_col, stretch=3)

        # Right column
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

        # Speed + System monitor
        bottom_right = QHBoxLayout()
        bottom_right.setSpacing(12)
        self.speed_widget = SpeedWidget(default_speed)
        bottom_right.addWidget(self.speed_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        self.system_monitor = SystemMonitorWidget()
        bottom_right.addWidget(self.system_monitor, alignment=Qt.AlignmentFlag.AlignCenter)
        right_col.addLayout(bottom_right)

        middle.addLayout(right_col, stretch=2)
        root.addLayout(middle, stretch=1)
        self._add_status_bar(root)

    # ── Prod Layout ───────────────────────────────────────────────

    def _build_prod_ui(self, num_lanes: int, default_speed: int):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(30, 20, 30, 20)
        root.setSpacing(20)

        # Header with mode badge
        header_row = QHBoxLayout()
        header = QLabel("SAFESPACE HIGHWAY MONITOR")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.setFont(QFont("Segoe UI", 18, QFont.Weight.Bold))
        header.setStyleSheet(f"color: {THEME_ACCENT}; letter-spacing: 3px; background: transparent;")
        header_row.addWidget(header, stretch=1)

        self.mode_badge = QLabel("NORMAL")
        self.mode_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mode_badge.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.mode_badge.setFixedSize(100, 28)
        self._set_mode_badge_style("normal")
        header_row.addWidget(self.mode_badge)
        root.addLayout(header_row)

        # Accident banner
        self.accident_banner = QLabel("⚠  ACCIDENT DETECTED  ⚠")
        self.accident_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.accident_banner.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.accident_banner.setStyleSheet(f"""
            background: rgba(255, 50, 50, 0.25);
            color: {THEME_DANGER};
            border: 2px solid {THEME_DANGER};
            border-radius: 10px;
            padding: 12px;
        """)
        self.accident_banner.setVisible(False)
        root.addWidget(self.accident_banner)

        # Lanes + Speed
        middle = QHBoxLayout()
        middle.setSpacing(20)

        lanes_frame = QFrame()
        lanes_layout = QHBoxLayout(lanes_frame)
        lanes_layout.setSpacing(15)
        self.lane_widgets: List[LaneWidget] = []
        for i in range(num_lanes):
            lane = LaneWidget(i)
            self.lane_widgets.append(lane)
            lanes_layout.addWidget(lane)
        middle.addWidget(lanes_frame, stretch=3)

        right = QVBoxLayout()
        right.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.speed_widget = SpeedWidget(default_speed)
        right.addWidget(self.speed_widget, alignment=Qt.AlignmentFlag.AlignHCenter)
        middle.addLayout(right, stretch=1)

        root.addLayout(middle, stretch=1)
        self._add_status_bar(root)

    # ── Shared helpers ────────────────────────────────────────────

    def _add_status_bar(self, root: QVBoxLayout):
        node_id = self.config.get('node.id', '?')
        desc = self.config.get('node.description', '')
        mode_tag = f"  •  Mode: {self._mode.upper()}"
        status = QLabel(f"Node {node_id}  •  {desc}{mode_tag}  •  Press SPACE to report manually")
        status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        status.setFont(QFont("Segoe UI", 9))
        status.setStyleSheet(f"color: {THEME_DIM}; background: transparent;")
        root.addWidget(status)

    def _set_mode_badge_style(self, mode: str):
        """Update the mode indicator badge."""
        styles = {
            "normal": ("background: rgba(0, 255, 136, 0.15); color: #00ff88; "
                       "border: 1px solid rgba(0, 255, 136, 0.4); border-radius: 6px;"),
            "streaming": ("background: rgba(255, 165, 0, 0.15); color: #ffa500; "
                          "border: 1px solid rgba(255, 165, 0, 0.4); border-radius: 6px;"),
            "degraded": ("background: rgba(255, 50, 50, 0.15); color: #ff4444; "
                         "border: 1px solid rgba(255, 50, 50, 0.4); border-radius: 6px;"),
        }
        self.mode_badge.setText(mode.upper())
        self.mode_badge.setStyleSheet(styles.get(mode, styles["normal"]))

    # ── Public API (called by DisplayApp) ─────────────────────────

    def update_lane(self, lane_index: int, status: str):
        if 0 <= lane_index < len(self.lane_widgets):
            self.lane_widgets[lane_index].set_status(status)

    def update_speed(self, limit: int):
        self.speed_widget.set_speed(limit)

    def set_accident_alert(self, active: bool):
        self.accident_banner.setVisible(active)
        self.speed_widget.set_alert_mode(active)
        if active:
            self._flash_timer.start(500)
        else:
            self._flash_timer.stop()
            self.accident_banner.setVisible(False)

    def update_mode(self, mode: str):
        """Update the mode indicator badge."""
        self._set_mode_badge_style(mode)

    def reset_display(self):
        for lane in self.lane_widgets:
            lane.set_status("up")
        self.speed_widget.set_speed(self._default_speed)
        self.speed_widget.set_alert_mode(False)
        self.accident_banner.setVisible(False)
        self._flash_timer.stop()

    def _flash_toggle(self):
        self._flash_visible = not self._flash_visible
        self.accident_banner.setVisible(self._flash_visible)

    # ── Keyboard ──────────────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and self.on_manual_trigger:
            self.on_manual_trigger()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        super().keyPressEvent(event)
