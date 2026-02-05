"""
Display Handler - Manages the Safespace Node Graphical User Interface.
Professional dark-themed UI using PyQt6.
"""
import sys
from pathlib import Path
from typing import Optional, Callable
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QFrame, QSizePolicy)
from PyQt6.QtSvgWidgets import QSvgWidget
from PyQt6.QtCore import Qt, QSize, pyqtSignal
from utils.constants import (DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT, 
                             ASPECT_RATIO, MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT,
                             LANE_STATUS_UP, LANE_STATUS_BLOCKED, 
                             LANE_STATUS_LEFT, LANE_STATUS_RIGHT, ROAD_SIGNS_DIR)


class DisplayHandler:
    """Orchestrator for the PyQt6 application and main window."""
    
    def __init__(self, config, on_manual_trigger: Optional[Callable] = None):
        """
        Initialize the display system.
        
        Args:
            config: Structured NodeConfig object
            on_manual_trigger: Callback for user interactions (e.g. spacebar)
        """
        self.config = config
        self.app = QApplication(sys.argv)
        self.window = MainWindow(config, on_manual_trigger=on_manual_trigger)

    def start(self):
        """Starts the GUI event loop. This call blocks."""
        self.window.show()
        sys.exit(self.app.exec())

    def update_lane_status(self, lane_index: int, status: str):
        """Thread-safe update of a specific lane sign."""
        self.window.update_lane_signal.emit(lane_index, status)

    def update_speed_limit(self, limit: int):
        """Thread-safe update of the speed limit indicator."""
        self.window.update_speed_signal.emit(limit)

    def set_accident_alert(self, active: bool):
        """Thread-safe toggle for the accident warning banner."""
        self.window.set_accident_signal.emit(active)
        
    def reset_display(self):
        """Thread-safe reset to default road state."""
        self.window.reset_display_signal.emit()


class MainWindow(QMainWindow):
    """The primary dashboard for highway status visualization."""
    
    # Thread-safe slots for cross-thread UI updates
    update_lane_signal = pyqtSignal(int, object)
    update_speed_signal = pyqtSignal(int)
    set_accident_signal = pyqtSignal(bool)
    reset_display_signal = pyqtSignal()

    def __init__(self, config, on_manual_trigger: Optional[Callable] = None):
        super().__init__()
        self.config = config
        self.on_manual_trigger = on_manual_trigger
        
        self.setProperty("class", "safespace-main")
        self._init_ui()
        self._setup_signals()

    def _init_ui(self):
        """Initialize the layout and styling of the dashboard."""
        self.setWindowTitle("Safespace | Node Dashboard")
        
        # Pull dimensions from config or constants
        width = self.config.get_int('display.width', DEFAULT_WINDOW_WIDTH)
        height = self.config.get_int('display.height', DEFAULT_WINDOW_HEIGHT)
        self.setGeometry(0, 0, width, height)
        
        self.aspect_ratio = ASPECT_RATIO
        self.setMinimumSize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0a0a0a, stop:1 #1a1a1a);
            }
        """)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(50)
        main_layout.setContentsMargins(60, 60, 60, 60)

        # --- Lanes Visualization ---
        lanes_container = QWidget()
        lanes_layout = QHBoxLayout(lanes_container)
        lanes_layout.setSpacing(40)
        lanes_layout.setContentsMargins(0, 0, 0, 0)
        
        self.lane_widgets = []
        lane_count = self.config.get_int('node.lanes', 3)
        for i in range(lane_count):
            lane = LaneWidget(i)
            lanes_layout.addWidget(lane, stretch=1)
            self.lane_widgets.append(lane)
            
        main_layout.addWidget(lanes_container, stretch=4)

        # --- Speed & Telemetry Section ---
        speed_container = QWidget()
        speed_container.setStyleSheet("background: rgba(255,255,255,0.06); border-radius: 20px; padding: 20px;")
        speed_layout = QHBoxLayout(speed_container)
        
        self._add_speed_labels(speed_layout)
        main_layout.addWidget(speed_container, stretch=1)

        # --- Critical Alert Banner ---
        self.accident_banner = self._create_alert_banner()
        main_layout.addWidget(self.accident_banner, stretch=0)
        
        self.set_default_state()

    def _setup_signals(self):
        """Connect thread-safe signals to internal UI methods."""
        self.update_lane_signal.connect(self.update_lane)
        self.update_speed_signal.connect(self.update_speed)
        self.set_accident_signal.connect(self.set_accident_alert)
        self.reset_display_signal.connect(self.set_default_state)

    def _add_speed_labels(self, layout):
        """Helper to build the speed telemetry row."""
        title = QLabel("SPEED LIMIT")
        title.setStyleSheet("color: white; font-size: 38px; font-weight: 200; letter-spacing: 4px;")
        layout.addWidget(title, stretch=1, alignment=Qt.AlignmentFlag.AlignRight)
        
        self.speed_label = QLabel("0")
        self.speed_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.speed_label.setStyleSheet("""
            background-color: #FFFFFF; color: #000000; border: 8px solid #FF3B3B;
            border-radius: 90px; font-size: 58px; font-weight: 800;
            min-height: 120px; max-height: 120px; min-width: 120px; max-width: 120px;
        """)
        layout.addWidget(self.speed_label, stretch=0)
        
        unit = QLabel("km/h")
        unit.setStyleSheet("color: #888888; font-size: 32px; font-weight: 300;")
        layout.addWidget(unit, stretch=1, alignment=Qt.AlignmentFlag.AlignLeft)

    def _create_alert_banner(self) -> QLabel:
        """Create the high-visibility warning banner."""
        banner = QLabel("⚠  ACCIDENT AHEAD  ⚠")
        banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        banner.setStyleSheet("""
            background: #FF0000; color: #FFFFFF; font-size: 60px; font-weight: 900;
            border: 4px solid #FFFFFF; border-radius: 12px; padding: 20px;
        """)
        banner.hide()
        return banner

    def set_default_state(self):
        """Revert the UI to standard highway operation mode."""
        default_speed = self.config.get_int('node.default_speed', 120)
        for i in range(len(self.lane_widgets)):
            self.update_lane(i, LANE_STATUS_UP)
        self.update_speed(default_speed)
        self.set_accident_alert(False)

    def resizeEvent(self, event):
        """Enforce aspect ratio scaling."""
        super().resizeEvent(event)
        new_width = event.size().width()
        expected_height = int(new_width / self.aspect_ratio)
        if abs(event.size().height() - expected_height) > 5:
            self.resize(new_width, expected_height)

    def update_lane(self, index, status):
        """Update visual representation of a lane."""
        if 0 <= index < len(self.lane_widgets):
            self.lane_widgets[index].set_status(status)

    def update_speed(self, limit):
        """Update the speed limit value."""
        self.speed_label.setText(str(limit))

    def set_accident_alert(self, active):
        """Toggle visibility of the accident warning."""
        self.accident_banner.setVisible(active)

    def keyPressEvent(self, event):
        """Bridge hardware keys (Spacebar) to reporting logic."""
        if event.key() == Qt.Key.Key_Space and self.on_manual_trigger:
            self.on_manual_trigger()
        else:
            super().keyPressEvent(event)


class LaneWidget(QFrame):
    """Visual component representing a single highway lane."""
    
    def __init__(self, lane_number):
        super().__init__()
        self.lane_number = lane_number
        self.assets_dir = ROAD_SIGNS_DIR
        
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.icon_widget = QSvgWidget()
        self.icon_widget.setMinimumSize(QSize(140, 140))
        
        layout = QVBoxLayout(self)
        layout.addWidget(self.icon_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        self.set_status(LANE_STATUS_UP)

    def set_status(self, status):
        """Update the lane status icon and border color."""
        if isinstance(status, dict):
            status = status.get('status', LANE_STATUS_UP)
            
        status = str(status).lower()
        icon_map = {
            LANE_STATUS_BLOCKED: 'blocked.svg',
            LANE_STATUS_UP: 'go_straight.svg',
            LANE_STATUS_LEFT: 'turn-left.svg',
            LANE_STATUS_RIGHT: 'turn-right.svg'
        }
        
        # Robust status mapping
        key = 'up'
        if 'block' in status: key = 'blocked'
        elif 'left' in status: key = 'left'
        elif 'right' in status: key = 'right'
        
        # Color themes
        themes = {
            'blocked': ("rgba(255, 50, 50, 0.6)", "rgba(255, 50, 50, 0.15)"),
            'left': ("rgba(255, 165, 0, 0.6)", "rgba(255, 165, 0, 0.15)"),
            'right': ("rgba(255, 165, 0, 0.6)", "rgba(255, 165, 0, 0.15)"),
            'up': ("rgba(0, 255, 136, 0.6)", "rgba(0, 255, 136, 0.15)")
        }
        border, bg = themes.get(key, themes['up'])
        
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg}; border: 3px solid {border}; border-radius: 18px;
            }}
        """)
        
        icon_path = self.assets_dir / icon_map.get(key, 'go_straight.svg')
        if icon_path.exists():
            self.icon_widget.load(str(icon_path))


if __name__ == "__main__":

    pass

