"""
Display Handler — public API that wraps QApplication + MainWindow.

This is the only class external code needs to import.
"""
import sys
from typing import Optional, Callable

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from utils.config import Config
from utils.logger import Logger

from handlers.display.main_window import MainWindow


class DisplayHandler:
    """
    Creates and manages the PyQt6 dashboard.

    Usage:
        display = DisplayHandler(config, on_manual_trigger=callback)

        # From any thread:
        display.update_lane_status(0, "blocked")
        display.update_speed_limit(60)
        display.set_accident_alert(True)
        display.push_input_frame(frame)   # dev mode only
        display.push_ai_frame(frame)      # dev mode only

        # Blocks (call on main thread):
        display.start()
    """

    def __init__(self, config: Config, on_manual_trigger: Optional[Callable] = None):
        self.config = config
        self.on_manual_trigger = on_manual_trigger
        self.logger = Logger("DisplayHandler")

        self._app: Optional[QApplication] = None
        self._window: Optional[MainWindow] = None

        # GPS indicator polling (set via set_gps_status_provider)
        self._gps_status_provider: Optional[Callable[[], bool]] = None
        self._gps_timer: Optional[QTimer] = None

    def start(self):
        """
        Start the Qt event loop.  **Blocks** until the window is closed.
        Call from the main thread.
        """
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._window = MainWindow(self.config, on_manual_trigger=self.on_manual_trigger)

        if self.config.get_bool('display.fullscreen', False):
            self._window.showFullScreen()
        else:
            self._window.show()

        # Periodically refresh the GPS indicator from the injected provider.
        # Runs on the Qt thread, so widget updates are safe.
        if self._gps_status_provider is not None:
            self._gps_timer = QTimer()
            self._gps_timer.timeout.connect(self._poll_gps_status)
            self._gps_timer.start(2000)  # every 2 seconds
            self._poll_gps_status()      # immediate first update

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

    def push_input_frame(self, frame):
        """Push a raw input frame to the dev feed. No-op in prod mode."""
        if self._window:
            self._window.push_input_frame(frame)

    def push_ai_frame(self, frame):
        """Push an AI-annotated frame to the dev feed. No-op in prod mode."""
        if self._window:
            self._window.push_ai_frame(frame)

    def reset_display(self):
        """Reset all UI elements to default state."""
        if self._window:
            self._window.reset_display()

    # ── GPS indicator ─────────────────────────────────────────────

    def set_gps_status_provider(self, provider: Callable[[], bool]):
        """Register a callable returning the current GPS fix status.
        It is polled on the Qt thread to keep the GPS indicator in sync."""
        self._gps_status_provider = provider

    def update_gps_status(self, has_fix: bool):
        """Update the GPS fix indicator (thread-safe via window signal)."""
        if self._window:
            self._window.update_gps_status(has_fix)

    def _poll_gps_status(self):
        """Read the provider and push the result to the GPS indicator."""
        if self._window and self._gps_status_provider is not None:
            try:
                self._window.update_gps_status(bool(self._gps_status_provider()))
            except Exception as e:
                self.logger.warning(f"GPS status poll failed: {e}")
