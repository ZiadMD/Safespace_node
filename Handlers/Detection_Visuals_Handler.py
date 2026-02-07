"""Detection Visuals Handler — draws bounding boxes and labels on frames.

Uses supervision's BoxAnnotator + LabelAnnotator (modern API).
Annotators are created once and reused for every frame.
"""
import numpy as np
import supervision as sv
from utils.logger import Logger


class DetectionVisualsHandler:
    """Annotates OpenCV frames with detection bounding boxes and labels."""

    def __init__(self, thickness: int = 2, text_scale: float = 0.5, text_thickness: int = 1):
        self.logger = Logger("DetectionVisualsHandler")
        self.box_annotator = sv.BoxAnnotator(thickness=thickness)
        self.label_annotator = sv.LabelAnnotator(
            text_scale=text_scale,
            text_thickness=text_thickness,
        )

    def visualize_detections(self, frame: np.ndarray, detections: sv.Detections) -> np.ndarray:
        """
        Draw bounding boxes and labels on the frame for the given detections.

        Args:
            frame: The input BGR image/frame to draw on (will be copied).
            detections: The detections to visualize.

        Returns:
            A new frame with visualized detections.
        """
        annotated = frame.copy()

        # Build labels from numpy arrays (modern supervision API)
        labels = []
        for i in range(len(detections)):
            class_id = int(detections.class_id[i]) if detections.class_id is not None else "?"
            conf = float(detections.confidence[i]) if detections.confidence is not None else 0.0
            labels.append(f"{class_id}: {conf:.2f}")

        annotated = self.box_annotator.annotate(scene=annotated, detections=detections)
        annotated = self.label_annotator.annotate(
            scene=annotated, detections=detections, labels=labels
        )

        self.logger.debug(f"Visualized {len(detections)} detections on frame.")
        return annotated