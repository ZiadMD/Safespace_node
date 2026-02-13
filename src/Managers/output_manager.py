"""
Output Manager — bridges AI detections and server events to the display.

Responsibilities:
  - Owns the DisplayHandler instance
  - Provides thread-safe methods for updating lanes, speed, accident alert
  - Receives AI detection callbacks and translates them to display updates
  - Receives server road-update events and applies them to the display
  - Starts the display (blocks on Qt event loop) in a controlled way

Usage from SafespaceNode:
    output = OutputManager(config)
    output.on_accident_detected(model_name, detections, frame)
    output.apply_road_update({"lanes": [...], "speed_limit": 60})
    output.start()  # BLOCKS — runs the Qt event loop
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional, Callable, Dict, Any

from utils.config import Config
from utils.logger import Logger
from Handlers.display_handler import DisplayHandler


class OutputManager:
    """
    Output Manager — translates detection events and server commands
    into display updates.
    """

    def __init__(self, config: Config, on_manual_trigger: Optional[Callable] = None):
        self.config = config
        self.logger = Logger("OutputManager")

        # Display handler
        self.display = DisplayHandler(config, on_manual_trigger=on_manual_trigger)

        # Track current state
        self._accident_active = False
        self._default_speed = config.get_int('node.default_speed', 120)
        self._num_lanes = config.get_int('node.lanes', 3)

        self.logger.info(f"Output Manager initialized ({self._num_lanes} lanes)")

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self):
        """
        Start the display. This BLOCKS (runs the Qt event loop).
        Should be called from the main thread after all other threads are started.
        """
        self.logger.info("Starting display...")
        self.display.start()

    # ── AI Detection Callback ─────────────────────────────────────

    def on_accident_detected(self, model_name: str, detections, frame):
        """
        Called when the AI Manager detects an accident.

        Args:
            model_name: Name of the model that fired
            detections: supervision.Detections object
            frame: The frame (numpy array) where the accident was seen
        """
        num = len(detections)
        self.logger.warning(f"Accident detected by [{model_name}]: {num} detection(s)")

        if not self._accident_active:
            self._accident_active = True
            self.display.set_accident_alert(True)

        # Show the frame that captured the accident
        self.display.show_accident_image(frame)

    # ── Server Road Update ────────────────────────────────────────

    def apply_road_update(self, data: Dict[str, Any]):
        """
        Apply a road-update payload from the central unit server.

        Expected payload format:
            {
                "lanes": ["up", "blocked", "left"],   # per-lane status
                "speed_limit": 60,                     # new speed limit
                "accident": true                       # whether accident mode is on
            }
        """
        self.logger.info(f"Applying road update: {data}")

        # Lane updates
        lanes = data.get("lanes", [])
        for i, status in enumerate(lanes):
            if i < self._num_lanes:
                self.display.update_lane_status(i, status)

        # Speed limit
        speed = data.get("speed_limit")
        if speed is not None:
            self.display.update_speed_limit(int(speed))

        # Accident flag
        accident = data.get("accident")
        if accident is not None:
            self._accident_active = bool(accident)
            self.display.set_accident_alert(self._accident_active)

    # ── Manual Controls ───────────────────────────────────────────

    def update_lane(self, lane_index: int, status: str):
        """Directly update a single lane."""
        self.display.update_lane_status(lane_index, status)

    def update_speed(self, limit: int):
        """Directly update the speed limit."""
        self.display.update_speed_limit(limit)

    def trigger_accident_alert(self, frame=None):
        """Manually trigger the accident alert."""
        self._accident_active = True
        self.display.set_accident_alert(True)
        if frame is not None:
            self.display.show_accident_image(frame)

    def clear_accident(self):
        """Clear the accident alert and reset display to normal."""
        self._accident_active = False
        self.display.reset_display()
        self.logger.info("Accident alert cleared — display reset")
