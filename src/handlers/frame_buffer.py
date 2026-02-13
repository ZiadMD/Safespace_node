"""
Frame Buffer — Thread-safe ring buffer that sits between input sources and consumers.

Architecture:
    [Camera / Video] --write_frame()--> [FrameBuffer] --get_latest() / get_clip()--> [AI / Recorder]

The buffer stores the last N frames (configurable) so that:
  - AI detection can grab the latest frame at any time.
  - A video recorder can pull a clip of the last K seconds after an event.
  - Multiple consumers can read independently without blocking the producer.
"""
import time
import threading
from collections import deque
from typing import Optional, List, Tuple
from dataclasses import dataclass, field
from cv2.typing import MatLike

from utils.config import Config
from utils.logger import Logger


@dataclass
class TimestampedFrame:
    """A frame with its capture timestamp."""
    frame: MatLike
    timestamp: float = field(default_factory=time.time)


class FrameBuffer:
    """
    Thread-safe ring buffer for video frames.

    Producers call `write_frame()` to push frames.
    Consumers call `get_latest()` for the newest frame,
    or `get_clip(seconds)` for a recent segment.
    """

    def __init__(self, config: Config):
        """
        Args:
            config: Application config. Reads from `buffer.*` keys:
                - buffer.max_seconds  : how many seconds of footage to keep (default 30)
                - buffer.fps_estimate : expected input FPS, used to size the deque (default from camera.fps)
        """
        self.logger = Logger("FrameBuffer")
        self.config = config

        max_seconds = self.config.get_int('buffer.max_seconds', 30)
        fps = self.config.get_int('camera.fps', 30)
        max_frames = max_seconds * fps

        self._buffer: deque[TimestampedFrame] = deque(maxlen=max_frames)
        self._lock = threading.Lock()
        self._frame_count = 0

        self.logger.info(f"Frame buffer created (capacity={max_frames} frames, ~{max_seconds}s @ {fps}fps)")

    # ── Producer API ──────────────────────────────────────────────

    def write_frame(self, frame: MatLike):
        """
        Push a new frame into the buffer. Called by the input source (camera/video).
        Old frames are automatically evicted when the buffer is full.
        """
        ts_frame = TimestampedFrame(frame=frame)
        with self._lock:
            self._buffer.append(ts_frame)
            self._frame_count += 1

    # ── Consumer API ──────────────────────────────────────────────

    def get_latest(self) -> Optional[MatLike]:
        """
        Get the most recent frame (non-blocking copy).
        Returns None if buffer is empty.
        """
        with self._lock:
            if not self._buffer:
                return None
            return self._buffer[-1].frame.copy()

    def get_latest_with_timestamp(self) -> Optional[Tuple[MatLike, float]]:
        """Get the most recent frame and its timestamp."""
        with self._lock:
            if not self._buffer:
                return None
            entry = self._buffer[-1]
            return entry.frame.copy(), entry.timestamp

    def get_clip(self, seconds: float) -> List[TimestampedFrame]:
        """
        Get the last `seconds` worth of frames as a list (oldest → newest).
        Useful for saving a recording clip after an incident is detected.

        Args:
            seconds: How many seconds of recent footage to retrieve.

        Returns:
            List of TimestampedFrame (copies). May be shorter than requested
            if the buffer hasn't accumulated enough data yet.
        """
        cutoff = time.time() - seconds
        with self._lock:
            clip = [
                TimestampedFrame(frame=entry.frame.copy(), timestamp=entry.timestamp)
                for entry in self._buffer
                if entry.timestamp >= cutoff
            ]
        return clip

    def get_frame_at(self, index: int) -> Optional[MatLike]:
        """
        Get a frame by its position in the buffer (0 = oldest, -1 = newest).
        Returns None if index is out of range.
        """
        with self._lock:
            try:
                return self._buffer[index].frame.copy()
            except IndexError:
                return None

    # ── Info ──────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        """Current number of frames in the buffer."""
        with self._lock:
            return len(self._buffer)

    @property
    def capacity(self) -> int:
        """Maximum number of frames the buffer can hold."""
        return self._buffer.maxlen or 0

    @property
    def total_frames_written(self) -> int:
        """Total frames written since creation (including evicted ones)."""
        return self._frame_count

    @property
    def duration_seconds(self) -> float:
        """Approximate duration of footage currently in the buffer."""
        with self._lock:
            if len(self._buffer) < 2:
                return 0.0
            return self._buffer[-1].timestamp - self._buffer[0].timestamp

    def clear(self):
        """Flush all frames from the buffer."""
        with self._lock:
            self._buffer.clear()
        self.logger.info("Buffer cleared")
