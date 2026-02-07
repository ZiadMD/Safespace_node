"""
Typed event definitions (messages) for the Safespace Node pipeline.

All inter-component communication happens through these dataclasses.
No component ever holds a direct reference to another — they
communicate via queues (pipeline) or the event bus (control plane).
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
import time
import numpy as np


# ─── Pipeline Messages (flow through Queue stages) ───────────────────────

@dataclass(frozen=True)
class Frame:
    """A captured video frame with metadata."""
    image: np.ndarray
    timestamp: float = field(default_factory=time.time)
    source: str = "unknown"  # "camera" or "video"


@dataclass(frozen=True)
class Detection:
    """Result of AI inference on a single frame."""
    model_name: str
    detections: Any           # sv.Detections object
    frame: np.ndarray         # The original frame that was analyzed
    confidence: float = 0.0   # Highest confidence in this batch
    timestamp: float = field(default_factory=time.time)


# ─── Event Bus Events (control plane, low-frequency) ─────────────────────

@dataclass
class AccidentDetected:
    """Published when an accident is confirmed (by AI or manual trigger)."""
    lane_number: str
    media_paths: Optional[List[str]] = None
    ai_detected: bool = False
    model_name: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ManualTrigger:
    """Published when the user presses the spacebar."""
    timestamp: float = field(default_factory=time.time)


@dataclass
class InstructionReceived:
    """Published when the Central Unit sends a road-state instruction."""
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class ConnectionStatus:
    """Published when network connection state changes."""
    connected: bool = False
    reason: str = ""
    timestamp: float = field(default_factory=time.time)


@dataclass
class ShutdownRequested:
    """Published to signal a graceful shutdown of all components."""
    reason: str = "user"
    timestamp: float = field(default_factory=time.time)


@dataclass
class DisplayUpdate:
    """Published when the display should change state."""
    action: str = ""        # "lane_status", "speed_limit", "accident_alert", "reset"
    lane_index: int = -1
    status: str = ""
    speed_limit: int = 0
    alert_active: bool = False
    timestamp: float = field(default_factory=time.time)
