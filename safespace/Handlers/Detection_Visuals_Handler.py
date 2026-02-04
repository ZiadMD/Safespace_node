# Manges BBox visualizations for detected objects
import cv2
import supervision as sv
from utils.logger import Logger
class DetectionVisualsHandler:
    def __init__(self):
        self.logger = Logger.get_logger("DetectionVisualsHandler")
    
    def visualize_detections(self, frame, detections: sv.Detections):
        """
        Draw bounding boxes and labels on the frame for the given detections.

        Args:
            frame (np.ndarray): The input image/frame to draw on.
            detections (sv.Detections): The detections to visualize.
        Returns:
            the frame with visualized detections.
        """

        box_annotator = sv.BoxAnnotator(
            thickness=2,
            text_thickness=1,
            text_scale=0.5
        )

        labels = [
            f"{detection.class_id}: {detection.confidence:.2f}"
            for detection in detections
        ]

        frame = box_annotator.annotate(
            scene=frame,
            detections=detections,
            labels=labels
        )

        self.logger.info(f"Visualized {len(detections)} detections on frame.")

        return frame