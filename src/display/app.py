"""
Display App — QApplication + pull-based rendering loop.

Instead of receiving frames via signals (v1), this app uses a QTimer
to pull the latest frame from shared memory every ~33ms. Messages from
the bus (detections, commands, mode changes) are drained on the same tick.
"""
import sys
from queue import Empty
from typing import Optional, Callable

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

from core.config import Config
from core.logger import Logger
from core.shared_memory import SharedFrameSlots
from core.message_bus import MessageBus
from core.constants import (
    TOPIC_DETECTION, TOPIC_ROAD_UPDATE, TOPIC_ACCIDENT_DECISION,
    TOPIC_MODE_CHANGED, BACKEND_LANE_STATUS_MAP, STATUS_CONFIRMED,
    STATUS_REJECTED,
)

from display.main_window import MainWindow


class DisplayApp:
    """
    Pull-based display manager.

    Usage:
        app = DisplayApp(config, shared_slots, bus)
        app.start()  # blocks (Qt event loop)
    """

    def __init__(
        self,
        config: Config,
        shared_slots: Optional[SharedFrameSlots],
        bus: Optional[MessageBus],
        on_manual_trigger: Optional[Callable] = None,
    ):
        self.config = config
        self.shared_slots = shared_slots
        self.bus = bus
        self.on_manual_trigger = on_manual_trigger
        self.logger = Logger("DisplayApp")

        self._app: Optional[QApplication] = None
        self._window: Optional[MainWindow] = None
        self._timer: Optional[QTimer] = None

        # Subscribe to bus topics
        self._detection_queue = bus.subscribe(TOPIC_DETECTION, maxsize=8) if bus else None
        self._road_update_queue = bus.subscribe(TOPIC_ROAD_UPDATE, maxsize=4) if bus else None
        self._accident_decision_queue = bus.subscribe(TOPIC_ACCIDENT_DECISION, maxsize=4) if bus else None
        self._mode_queue = bus.subscribe(TOPIC_MODE_CHANGED, maxsize=4) if bus else None

        # Tracking
        self._last_input_fid = -1
        self._last_annotated_ts = 0.0

    def start(self):
        """Start the Qt event loop. Blocks until the window is closed."""
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._window = MainWindow(self.config, on_manual_trigger=self.on_manual_trigger)

        # Pull timer — renders at ~30 FPS
        self._timer = QTimer()
        self._timer.timeout.connect(self._render_tick)
        self._timer.start(33)

        if self.config.get_bool('display.fullscreen', False):
            self._window.showFullScreen()
        else:
            self._window.show()

        self.logger.info("Display started (pull-based, 30 FPS)")
        self._app.exec()

    def _render_tick(self):
        """Called every 33ms — pull latest frames and drain message queues."""
        self._pull_frames()
        self._drain_messages()

    def _pull_frames(self):
        """Pull latest frames directly from shared memory."""
        if self.shared_slots is None or self._window is None:
            return

        # Input feed (dev mode only)
        if self._window.input_feed is not None:
            result = self.shared_slots.read_latest()
            if result is not None:
                frame, ts, fid = result
                if fid != self._last_input_fid:
                    self._last_input_fid = fid
                    self._window.input_feed.render_frame(frame)

        # AI annotated feed (dev mode only)
        if self._window.ai_feed is not None:
            result = self.shared_slots.read_annotated()
            if result is not None:
                ann_frame, ann_ts = result
                if ann_ts > self._last_annotated_ts:
                    self._last_annotated_ts = ann_ts
                    self._window.ai_feed.render_frame(ann_frame)

    def _drain_messages(self):
        """Non-blocking drain of all bus message queues."""
        if self._window is None:
            return

        # Detection events
        if self._detection_queue:
            self._drain_queue(self._detection_queue, self._handle_detection)

        # Road updates from server
        if self._road_update_queue:
            self._drain_queue(self._road_update_queue, self._handle_road_update)

        # Accident decisions from server
        if self._accident_decision_queue:
            self._drain_queue(self._accident_decision_queue, self._handle_accident_decision)

        # Mode changes
        if self._mode_queue:
            self._drain_queue(self._mode_queue, self._handle_mode_change)

    @staticmethod
    def _drain_queue(queue, handler):
        """Drain all messages from a queue and call the handler."""
        for _ in range(50):
            try:
                msg = queue.get_nowait()
                handler(msg)
            except Empty:
                break
            except Exception:
                break

    def _handle_detection(self, msg: dict):
        """AI detected something — show accident alert."""
        self._window.set_accident_alert(True)

    def _handle_road_update(self, msg: dict):
        """Server sent a road state update — update lanes and speed."""
        lanes = msg.get("lanes", [])
        for i, lane_data in enumerate(lanes):
            if isinstance(lane_data, dict):
                status = lane_data.get("status", "open")
            else:
                status = str(lane_data)
            mapped = BACKEND_LANE_STATUS_MAP.get(status, "up")
            self._window.update_lane(i, mapped)

        speed = msg.get("speed_limit")
        if speed is not None:
            self._window.update_speed(int(speed))

        accident = msg.get("accident")
        if accident is not None:
            self._window.set_accident_alert(bool(accident))

    def _handle_accident_decision(self, msg: dict):
        """Server made a decision about an accident."""
        status = msg.get("status", "")
        if status == STATUS_REJECTED:
            self._window.set_accident_alert(False)
            self._window.reset_display()

    def _handle_mode_change(self, msg: dict):
        """Operating mode changed — update the badge."""
        mode = msg.get("mode", "normal")
        self._window.update_mode(mode)
