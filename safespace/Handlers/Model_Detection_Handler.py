from ultralytics import YOLO
from inference.core.models.base import Model
import supervision as sv
from cv2.typing import MatLike
import torch

class ModelDetectionHandler:

    def yolo_detect(self, model: YOLO, confidence: float, frame: MatLike) -> list:
        """
        Perform object detection on a given frame using the YOLO model.

        Args:
            model (YOLO): The loaded YOLO model.
            frame: The input frame/image for detection.
            confidence (float): Confidence threshold for detections.

        Returns:
            List of detection results.
        """

        results = model.predict(frame, conf=confidence, verbose=False)
        detections = results.xyxy[0].cpu().numpy().tolist()  # Convert to list of detections
        return detections