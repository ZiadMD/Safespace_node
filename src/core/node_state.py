"""
Node State Machine — manages operating mode transitions.

Modes:
    NORMAL    — AI runs locally, only alerts sent to server
    STREAMING — AI down, raw video streamed to Central Unit
    DEGRADED  — AI down + server unreachable, local buffer only
"""
import time
from enum import Enum
from typing import Callable, List, Optional

from core.logger import Logger


class Mode(Enum):
    NORMAL = "normal"
    STREAMING = "streaming"
    DEGRADED = "degraded"


class NodeState:
    """
    Manages the current operating mode with valid transitions.

    Transition rules:
        NORMAL    → STREAMING  (AI failed)
        STREAMING → NORMAL     (AI recovered)
        STREAMING → DEGRADED   (server also unreachable)
        DEGRADED  → STREAMING  (server came back)
        DEGRADED  → NORMAL     (AI recovered)
    """

    VALID_TRANSITIONS = {
        Mode.NORMAL:    [Mode.STREAMING],
        Mode.STREAMING: [Mode.NORMAL, Mode.DEGRADED],
        Mode.DEGRADED:  [Mode.STREAMING, Mode.NORMAL],
    }

    def __init__(self):
        self.logger = Logger("NodeState")
        self._mode = Mode.NORMAL
        self._listeners: List[Callable] = []
        self._transition_log: List[dict] = []

    @property
    def mode(self) -> Mode:
        return self._mode

    def on_transition(self, callback: Callable):
        """Register a callback for mode transitions: callback(old_mode, new_mode)."""
        self._listeners.append(callback)

    def transition_to(self, new_mode: Mode) -> bool:
        """
        Attempt a mode transition.

        Returns True if the transition was valid and executed.
        Returns False if the transition is not allowed.
        """
        if new_mode == self._mode:
            return True  # already in this mode

        if new_mode not in self.VALID_TRANSITIONS.get(self._mode, []):
            self.logger.warning(
                f"Invalid transition: {self._mode.value} → {new_mode.value}"
            )
            return False

        old = self._mode
        self._mode = new_mode
        self._transition_log.append({
            "from": old.value,
            "to": new_mode.value,
            "time": time.time(),
        })

        self.logger.info(f"Mode transition: {old.value} → {new_mode.value}")

        for listener in self._listeners:
            try:
                listener(old, new_mode)
            except Exception as e:
                self.logger.error(f"Transition listener error: {e}")

        return True

    @property
    def is_normal(self) -> bool:
        return self._mode == Mode.NORMAL

    @property
    def is_streaming(self) -> bool:
        return self._mode == Mode.STREAMING

    @property
    def is_degraded(self) -> bool:
        return self._mode == Mode.DEGRADED

    @property
    def transition_history(self) -> List[dict]:
        return list(self._transition_log)
