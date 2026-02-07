"""
Display Subscriber — bridges EventBus events to the PyQt6 DisplayHandler.

Subscribes to DisplayUpdate events from the bus and routes them
to the correct Qt signal on the DisplayHandler. This keeps the
display completely decoupled from the pipeline and decision logic.
"""
from core.bus import EventBus
from core.events import DisplayUpdate
from Handlers.Display_Handler import DisplayHandler
from utils.logger import Logger


class DisplaySubscriber:
    """
    Subscribes to DisplayUpdate events and translates them
    into thread-safe Qt signal calls on the DisplayHandler.
    """

    def __init__(self, bus: EventBus, display: DisplayHandler):
        """
        Args:
            bus: Shared event bus.
            display: The DisplayHandler (wraps Qt window).
        """
        self.bus = bus
        self.display = display
        self.logger = Logger("DisplaySubscriber")

        # Subscribe
        self.bus.subscribe(DisplayUpdate, self._on_display_update)

    def _on_display_update(self, event: DisplayUpdate) -> None:
        """Route display update events to the correct Qt signal."""
        try:
            action = event.action

            if action == "lane_status":
                self.display.update_lane_status(event.lane_index, event.status)

            elif action == "speed_limit":
                self.display.update_speed_limit(event.speed_limit)

            elif action == "accident_alert":
                self.display.set_accident_alert(event.alert_active)

            elif action == "reset":
                self.display.reset_display()

            else:
                self.logger.warning(f"Unknown display action: {action}")

        except Exception as e:
            self.logger.error(f"Display update error: {e}")
