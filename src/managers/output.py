"""
Output Manager — bridges AI detections and server events to the display.

Responsibilities:
  - Owns the DisplayHandler instance
  - Provides thread-safe methods for updating lanes, speed, accident alert
  - Receives AI detection callbacks and translates them to display updates
  - Receives server road-update events and applies them to the display
  - Forwards raw / annotated frames to the display (dev mode feeds)
  - Starts the display (blocks on Qt event loop) in a controlled way

Usage from SafespaceNode:
    output = OutputManager(config)
    output.on_accident_detected(model_name, detections, frame)
    output.apply_road_update({"lanes": [...], "speed_limit": 60})
    output.push_input_frame(frame)
    output.push_ai_frame(annotated_frame)
    output.start()  # BLOCKS — runs the Qt event loop
"""
from typing import Optional, Callable, Dict, Any

from utils.config import Config
from utils.logger import Logger
from handlers.display import DisplayHandler


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

    # ── Frame Feeds (dev mode) ────────────────────────────────────

    def push_input_frame(self, frame):
        """Forward a raw input frame to the display. No-op in prod mode."""
        self.display.push_input_frame(frame)

    def push_ai_frame(self, frame):
        """Forward an AI-annotated frame to the display. No-op in prod mode."""
        self.display.push_ai_frame(frame)

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

    def on_imx500_detected(self, detections, frame):
        """
        Called when IMX500 on-chip inference produces detections.

        Args:
            detections: supervision.Detections object or None
            frame: The annotated frame (numpy array) to push to display
        """
        num = len(detections) if detections is not None else 0
        if num > 0:
            self.logger.warning(f"IMX500 UI Alert: {num} object(s)")
            if not self._accident_active:
                self._accident_active = True
                self.display.set_accident_alert(True)
        # Push annotated frame to display for visualization
        self.display.push_ai_frame(frame)

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

    def trigger_accident_alert(self):
        """Manually trigger the accident alert."""
        self._accident_active = True
        self.display.set_accident_alert(True)

    def clear_accident(self):
        """Clear the accident alert and reset display to normal."""
        self._accident_active = False
        self.display.reset_display()
        self.logger.info("Accident alert cleared — display reset")
