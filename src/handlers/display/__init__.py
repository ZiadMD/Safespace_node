"""
Display package — Safespace PyQt6 dashboard.

Modules:
    lane_widget           — LaneWidget (SVG icon + status per lane)
    speed_widget          — SpeedWidget (speed limit circle)
    video_feed_widget     — VideoFeedWidget (live frame + FPS overlay)
    system_monitor_widget — SystemMonitorWidget (CPU/MEM gauge)
    main_window           — MainWindow (dev / prod layouts, signals, slots)
    display_handler       — DisplayHandler (public API)
"""
from handlers.display.display_handler import DisplayHandler
from handlers.display.lane_widget import LaneWidget
from handlers.display.speed_widget import SpeedWidget
from handlers.display.video_feed_widget import VideoFeedWidget
from handlers.display.system_monitor_widget import SystemMonitorWidget
from handlers.display.main_window import MainWindow

__all__ = [
    "DisplayHandler",
    "LaneWidget",
    "SpeedWidget",
    "VideoFeedWidget",
    "SystemMonitorWidget",
    "MainWindow",
]
