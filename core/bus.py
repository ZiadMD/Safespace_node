"""
Lightweight in-process Event Bus for the Safespace Node.

Handles the control-plane: low-frequency events like accident reports,
server instructions, manual triggers, connection changes, and shutdown.

Thread-safe. Handlers are invoked synchronously on the publisher's thread
by default, or can be dispatched to a thread pool for heavy work.
"""
import threading
from collections import defaultdict
from typing import Callable, Any, Dict, List, Type
from utils.logger import Logger


class EventBus:
    """
    Simple publish/subscribe event bus.
    
    Usage:
        bus = EventBus()
        bus.subscribe(AccidentDetected, my_handler)
        bus.publish(AccidentDetected(lane="1", media=[...]))
    """

    def __init__(self):
        self._subscribers: Dict[Type, List[Callable]] = defaultdict(list)
        self._lock = threading.Lock()
        self.logger = Logger("EventBus")

    def subscribe(self, event_type: Type, handler: Callable[[Any], None]) -> None:
        """
        Register a handler for a specific event type.
        
        Args:
            event_type: The class of the event to listen for.
            handler: A callable that receives the event instance.
        """
        with self._lock:
            self._subscribers[event_type].append(handler)
            self.logger.debug(f"Subscribed {handler.__qualname__} to {event_type.__name__}")

    def unsubscribe(self, event_type: Type, handler: Callable[[Any], None]) -> None:
        """Remove a handler from a specific event type."""
        with self._lock:
            handlers = self._subscribers.get(event_type, [])
            if handler in handlers:
                handlers.remove(handler)

    def publish(self, event: Any) -> None:
        """
        Publish an event to all registered handlers.
        
        Handlers are called synchronously on the caller's thread.
        Exceptions in one handler do not prevent other handlers from running.
        
        Args:
            event: An instance of a dataclass event (e.g., AccidentDetected(...)).
        """
        event_type = type(event)
        with self._lock:
            handlers = self._subscribers.get(event_type, []).copy()

        if not handlers:
            self.logger.debug(f"No subscribers for {event_type.__name__}")
            return

        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                self.logger.error(
                    f"Error in handler {handler.__qualname__} for "
                    f"{event_type.__name__}: {e}"
                )

    def clear(self) -> None:
        """Remove all subscriptions."""
        with self._lock:
            self._subscribers.clear()

    def subscriber_count(self, event_type: Type) -> int:
        """Return the number of subscribers for a given event type."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))
