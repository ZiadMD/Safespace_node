from ultralytics import YOLO
from cv2.typing import MatLike
import supervision as sv
import torch
from utils.logger import Logger


class ModelDetectionHandler:
    """Handler for YOLO model detection with automatic GPU/CPU selection."""

    def __init__(self):
        self.logger = Logger("ModelDetectionHandler")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.logger.info(f"Using device: {self.device}")

    def detect(self, model: YOLO, frame: MatLike, confidence: float = 0.5) -> sv.Detections:
        """
        Perform object detection on a given frame using the YOLO model.

        Args:
            model (YOLO): The loaded YOLO model.
            frame (MatLike): The input frame/image for detection.
            confidence (float): Confidence threshold for detections (default: 0.5).

        Returns:
            sv.Detections: Supervision Detections object containing bounding boxes,
                           confidence scores, and class IDs.
        """
        results = model.predict(frame, conf=confidence, device=self.device, verbose=False)
        return sv.Detections.from_ultralytics(results[0])