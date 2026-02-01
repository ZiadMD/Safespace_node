from ultralytics import YOLO
from inference.core.models.base import Model
import supervision as sv
from cv2.typing import MatLike

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
    
    def roboflow_detect(self, model: Model, confidence: float, frame: MatLike) -> list:
        """
        Perform object detection on a given frame using the Roboflow model.

        Args:
            model (Model): The loaded Roboflow model.
            confidence (float): Confidence threshold for detections.
            frame: The input frame/image for detection.

        Returns:
            List of detection results.
        """
        predictions = model.infer(frame, conf=confidence)[0]
        detections = sv.Detections.from_inference(predictions)
        return detections