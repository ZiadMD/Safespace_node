"""
Protocol definitions (interfaces) for the Safespace Node.

These define the contracts that adapters must implement,
enabling dependency injection and easy testing/swapping.
"""
from typing import Protocol, Optional, Dict, Any, runtime_checkable
import numpy as np


@runtime_checkable
class FrameSource(Protocol):
    """Interface for any frame-producing component (camera, video file, etc.)."""

    def start(self) -> bool:
        """Initialize and begin frame acquisition. Returns True on success."""
        ...

    def read_frame(self) -> Optional[np.ndarray]:
        """
        Read the next available frame.
        
        Returns:
            A BGR numpy array (OpenCV format), or None if no frame is available.
        """
        ...

    def stop(self) -> None:
        """Release resources and stop frame acquisition."""
        ...


@runtime_checkable
class Detector(Protocol):
    """Interface for any AI detection backend (YOLO, custom model, etc.)."""

    def detect(self, frame: np.ndarray, confidence: float = 0.5) -> Any:
        """
        Run inference on a single frame.
        
        Args:
            frame: BGR numpy array.
            confidence: Minimum confidence threshold.
            
        Returns:
            A supervision.Detections object (or compatible).
        """
        ...


@runtime_checkable
class Reporter(Protocol):
    """Interface for reporting accidents to external systems."""

    def report(self, payload: Dict[str, Any], media_paths: Optional[list] = None) -> bool:
        """
        Send an accident report.
        
        Args:
            payload: Dictionary with nodeId, lat, long, laneNumber, etc.
            media_paths: Optional list of image/video file paths to attach.
            
        Returns:
            True if the report was sent successfully.
        """
        ...

    def connect(self) -> bool:
        """Establish connection to the remote server."""
        ...

    def disconnect(self) -> None:
        """Cleanly close the connection."""
        ...

    def emit_heartbeat(self, node_id: str) -> None:
        """Send a keep-alive signal."""
        ...
