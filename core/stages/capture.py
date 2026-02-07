"""
Capture Stage — reads frames from a FrameSource and puts them into the frame queue.

Runs in its own thread. Uses put_nowait() so that if the inference stage
is busy, stale frames are dropped (bounded queue backpressure).
"""
import time
from queue import Queue, Full
from threading import Thread, Event
from typing import Optional

from core.events import Frame
from core.protocols import FrameSource
from utils.logger import Logger


class CaptureStage(Thread):
    """
    Pipeline Stage 0: Frame acquisition.
    
    Reads frames from any FrameSource (camera, video file, etc.)
    and pushes them into a bounded queue for downstream processing.
    """

    def __init__(
        self,
        source: FrameSource,
        out_queue: Queue,
        stop_event: Event,
        fps: int = 30,
        loop_video: bool = True,
        source_type: str = "unknown",
    ):
        """
        Args:
            source: Any object implementing the FrameSource protocol.
            out_queue: Bounded queue to push Frame messages into.
            stop_event: Shared threading.Event — set to signal shutdown.
            fps: Target frame rate for capture loop timing.
            loop_video: If True and source is a video file, restart on EOF.
            source_type: "camera" or "video" — attached to Frame metadata.
        """
        super().__init__(name="CaptureStage", daemon=True)
        self.source = source
        self.out_queue = out_queue
        self.stop_event = stop_event
        self.fps = fps
        self.loop_video = loop_video
        self.source_type = source_type
        self.logger = Logger("CaptureStage")

    def run(self) -> None:
        """Main capture loop — runs until stop_event is set."""
        if not self.source.start():
            self.logger.error("Frame source failed to start")
            return

        self.logger.info(f"Capture stage running ({self.source_type}, {self.fps} FPS target)")
        frame_interval = 1.0 / max(self.fps, 1)

        while not self.stop_event.is_set():
            loop_start = time.monotonic()

            raw_frame = self.source.read_frame()

            if raw_frame is None:
                # End of source (video file ended, camera dropped, etc.)
                if self.source_type == "video" and self.loop_video:
                    self.logger.info("Video ended — looping back to start")
                    self.source.stop()
                    if not self.source.start():
                        self.logger.error("Failed to restart video source")
                        break
                    continue
                elif self.source_type == "video":
                    self.logger.info("Video playback finished")
                    break
                else:
                    # Camera glitch — brief retry
                    time.sleep(0.1)
                    continue

            frame_msg = Frame(image=raw_frame, source=self.source_type)

            # Drop-on-full policy: if inference is busy, discard stale frame
            try:
                self.out_queue.put_nowait(frame_msg)
            except Full:
                # Queue is full — drop this frame (natural backpressure)
                pass

            # Precise frame-rate timing (subtract processing time)
            elapsed = time.monotonic() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        # Cleanup
        self.source.stop()
        self.logger.info("Capture stage stopped")
