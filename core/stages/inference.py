"""
Inference Stage — pulls frames from the frame queue, runs YOLO detection,
and pushes results into the detection queue.

Runs in its own thread. This is where the heavy GPU/CPU work happens,
completely decoupled from frame capture timing.
"""
import cv2
from queue import Queue, Empty, Full
from threading import Thread, Event
from typing import Dict, Any, Optional

from core.events import Frame, Detection
from utils.logger import Logger


class InferenceStage(Thread):
    """
    Pipeline Stage 1: AI inference.
    
    Consumes Frame messages, runs one or more YOLO models,
    and produces Detection messages for downstream processing.
    """

    def __init__(
        self,
        in_queue: Queue,
        out_queue: Queue,
        stop_event: Event,
        models: Dict[str, Dict[str, Any]],
        detection_handler: Any,
        viewer_queue: Optional[Queue] = None,
        visuals_handler: Any = None,
    ):
        """
        Args:
            in_queue: Queue of Frame messages from CaptureStage.
            out_queue: Queue of Detection messages for DecisionStage.
            stop_event: Shared threading.Event for shutdown.
            models: Dict mapping model_name -> {"model": YOLO, "confidence": float}
            detection_handler: ModelDetectionHandler instance for running predictions.
            viewer_queue: Optional bounded queue — receives annotated (or raw) frames
                          for the frame-viewer window.
            visuals_handler: Optional DetectionVisualsHandler for drawing bounding boxes.
        """
        super().__init__(name="InferenceStage", daemon=True)
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.stop_event = stop_event
        self.models = models
        self.detection_handler = detection_handler
        self.viewer_queue: Optional[Queue] = viewer_queue
        self.visuals_handler = visuals_handler
        self.logger = Logger("InferenceStage")

    def run(self) -> None:
        """Main inference loop — blocks on input queue, processes, pushes results."""
        self.logger.info(f"Inference stage running with {len(self.models)} model(s)")

        while not self.stop_event.is_set():
            # Block with timeout so we can check stop_event periodically
            try:
                frame_msg: Frame = self.in_queue.get(timeout=0.5)
            except Empty:
                continue

            # Start with the raw frame; overlay detections if any
            display_frame = frame_msg.image
            any_detections = False

            # Run inference with each loaded model
            for model_name, model_data in self.models.items():
                try:
                    model = model_data["model"]
                    confidence = model_data.get("confidence", 0.5)

                    detections = self.detection_handler.detect(
                        model, frame_msg.image, confidence
                    )

                    if detections is not None and len(detections) > 0:
                        any_detections = True

                        # Find max confidence in this detection batch
                        max_conf = 0.0
                        if hasattr(detections, 'confidence') and detections.confidence is not None:
                            max_conf = float(detections.confidence.max())

                        detection_msg = Detection(
                            model_name=model_name,
                            detections=detections,
                            frame=frame_msg.image,
                            confidence=max_conf,
                            timestamp=frame_msg.timestamp,
                        )

                        try:
                            self.out_queue.put_nowait(detection_msg)
                        except Full:
                            self.logger.warning("Detection queue full — dropping result")

                        # Annotate the viewer frame with bounding boxes
                        if self.visuals_handler is not None:
                            try:
                                display_frame = self.visuals_handler.visualize_detections(
                                    display_frame, detections
                                )
                            except Exception as e:
                                self.logger.warning(f"Visualization error: {e}")

                except Exception as e:
                    self.logger.error(f"Inference error in model '{model_name}': {e}")

            # Push latest frame with HUD overlay to viewer window
            if self.viewer_queue is not None:
                viewer_frame = self._draw_hud(display_frame, any_detections)
                try:
                    self.viewer_queue.put_nowait(viewer_frame)
                except Full:
                    pass  # Viewer is behind — drop

        self.logger.info("Inference stage stopped")

    def _draw_hud(self, frame, detected: bool) -> 'np.ndarray':
        """Overlay a small AI-status banner on the top-left of the frame."""
        out = frame.copy()
        h, w = out.shape[:2]

        model_names = ", ".join(self.models.keys())
        status = "DETECTED" if detected else "scanning"
        color = (0, 0, 255) if detected else (0, 200, 0)  # red / green (BGR)

        text = f"AI [{model_names}]: {status}"
        cv2.putText(out, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, (0, 0, 0), 3, cv2.LINE_AA)  # shadow
        cv2.putText(out, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                    0.7, color, 2, cv2.LINE_AA)
        return out
