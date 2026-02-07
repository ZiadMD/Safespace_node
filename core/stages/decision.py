"""
Decision Stage — consumes AI detections and manual triggers,
applies business rules, and publishes events to the event bus.

This is the ONLY component that owns the `awaiting_confirmation` state,
eliminating the race condition from the old architecture.
"""
import cv2
import time
from queue import Queue, Empty
from threading import Thread, Event, Lock
from typing import Optional
from datetime import datetime

from core.bus import EventBus
from core.events import (
    Detection, AccidentDetected, ManualTrigger,
    InstructionReceived, DisplayUpdate, ShutdownRequested,
)
from utils.logger import Logger
from utils.constants import ACCIDENT_IMAGES_DIR


class DecisionStage(Thread):
    """
    Pipeline Stage 2: Business logic and decision-making.
    
    Owns the awaiting_confirmation flag exclusively (no race conditions).
    Consumes from the detection queue and manual trigger events,
    then publishes AccidentDetected and DisplayUpdate events to the bus.
    """

    def __init__(
        self,
        detection_queue: Queue,
        bus: EventBus,
        stop_event: Event,
        config: dict,
    ):
        """
        Args:
            detection_queue: Queue of Detection messages from InferenceStage.
            bus: EventBus for publishing events (AccidentDetected, DisplayUpdate).
            stop_event: Shared threading.Event for shutdown.
            config: Full application config dict.
        """
        super().__init__(name="DecisionStage", daemon=True)
        self.detection_queue = detection_queue
        self.bus = bus
        self.stop_event = stop_event
        self.config = config
        self.logger = Logger("DecisionStage")

        # State — exclusively owned by this thread (no races)
        self._awaiting_confirmation = False
        self._lock = Lock()  # For manual trigger calls from Qt thread

        # Latest frame for manual trigger snapshots
        self._latest_frame = None
        self._frame_lock = Lock()

        # Subscribe to control-plane events
        self.bus.subscribe(ManualTrigger, self._on_manual_trigger)
        self.bus.subscribe(InstructionReceived, self._on_instruction)

    @property
    def awaiting_confirmation(self) -> bool:
        with self._lock:
            return self._awaiting_confirmation

    @awaiting_confirmation.setter
    def awaiting_confirmation(self, value: bool):
        with self._lock:
            self._awaiting_confirmation = value

    def update_latest_frame(self, frame):
        """Called by capture stage or frame distributor to keep a snapshot reference."""
        with self._frame_lock:
            self._latest_frame = frame

    def run(self) -> None:
        """Main decision loop — process detections and apply business rules."""
        self.logger.info("Decision stage running")

        while not self.stop_event.is_set():
            try:
                detection: Detection = self.detection_queue.get(timeout=0.5)
            except Empty:
                continue

            # Update latest frame for potential snapshots
            self.update_latest_frame(detection.frame)

            self._handle_detection(detection)

        self.logger.info("Decision stage stopped")

    def _handle_detection(self, detection: Detection) -> None:
        """Apply business rules to an AI detection result."""
        if self.awaiting_confirmation:
            self.logger.debug("Detection ignored — awaiting confirmation from Central Unit")
            return

        self.logger.info(
            f"AI Detection from '{detection.model_name}': "
            f"{len(detection.detections)} object(s), "
            f"max confidence {detection.confidence:.2f}"
        )

        # Only act on accident-related models
        if "accident" not in detection.model_name.lower():
            return

        self.logger.warning(f"🚨 Accident detected by '{detection.model_name}'!")
        self.awaiting_confirmation = True

        # Save snapshot
        snapshot_path = self._save_snapshot(detection.frame, prefix="ai_detection")
        media = [snapshot_path] if snapshot_path else None

        # Determine lane (TODO: implement lane detection logic)
        lane_number = "1"

        # Publish to event bus — NetworkWorker will handle reporting
        self.bus.publish(AccidentDetected(
            lane_number=lane_number,
            media_paths=media,
            ai_detected=True,
            model_name=detection.model_name,
        ))

    def _on_manual_trigger(self, event: ManualTrigger) -> None:
        """Handle spacebar press — called from Qt thread via event bus."""
        if self.awaiting_confirmation:
            self.logger.warning("Manual trigger ignored — already awaiting confirmation")
            return

        self.logger.info("Manual accident report triggered by user")
        self.awaiting_confirmation = True

        # Save snapshot from latest frame
        with self._frame_lock:
            frame = self._latest_frame.copy() if self._latest_frame is not None else None

        snapshot_path = self._save_snapshot(frame, prefix="manual_report") if frame is not None else None
        media = [snapshot_path] if snapshot_path else None

        lane_number = "1"

        self.bus.publish(AccidentDetected(
            lane_number=lane_number,
            media_paths=media,
            ai_detected=False,
        ))

    def _on_instruction(self, event: InstructionReceived) -> None:
        """Handle instructions from the Central Unit — reset awaiting state, update display."""
        data = event.data
        self.logger.info(f"Central Unit instruction received: {data}")

        # Reset awaiting state
        self.awaiting_confirmation = False

        # Parse and publish display updates
        is_accident = data.get("isAccident", False)

        if not is_accident:
            # Reset display to default
            self.bus.publish(DisplayUpdate(action="reset"))
        else:
            # Show accident alert
            self.bus.publish(DisplayUpdate(action="accident_alert", alert_active=True))

        # Update speed limit if provided
        speed_limit = data.get("speedLimit")
        if speed_limit is not None:
            try:
                self.bus.publish(DisplayUpdate(
                    action="speed_limit",
                    speed_limit=int(speed_limit),
                ))
            except (ValueError, TypeError):
                pass

        # Update lane states if provided
        lane_states = data.get("laneStates", [])
        for i, state in enumerate(lane_states):
            status = state if isinstance(state, str) else state.get("status", "up")
            self.bus.publish(DisplayUpdate(
                action="lane_status",
                lane_index=i,
                status=status,
            ))

    def _save_snapshot(self, frame, prefix: str = "snapshot") -> Optional[str]:
        """Save a frame to disk and return the file path."""
        if frame is None:
            return None

        try:
            ACCIDENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{prefix}_{timestamp}.jpg"
            save_path = str(ACCIDENT_IMAGES_DIR / filename)

            if cv2.imwrite(save_path, frame):
                self.logger.info(f"Snapshot saved: {save_path}")
                return save_path
            else:
                self.logger.error(f"cv2.imwrite failed for: {save_path}")
        except Exception as e:
            self.logger.error(f"Failed to save snapshot: {e}")

        return None
