"""
Model Detection Handler - Runs inference on a single frame using a loaded YOLO model.

Responsible only for:
  - Running model.track() or model.predict() on a frame
  - Converting raw YOLO results into supervision Detections
  - Filtering detections by target classes and confidence
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import supervision as sv
from typing import Optional, List, Any
from cv2.typing import MatLike
from utils.logger import Logger


class ModelDetectionHandler:
    """Runs YOLO inference and returns structured detections."""

    def __init__(self):
        self.logger = Logger("DetectionHandler")

    def detect(
        self,
        model: Any,
        frame: MatLike,
        confidence: float = 0.5,
        target_classes: Optional[List[str]] = None,
        use_tracking: bool = True,
        tracker: str = "botsort.yaml",
        persist: bool = True,
    ) -> sv.Detections:
        """
        Run inference on a frame and return filtered detections.
        
        Args:
            model: A loaded YOLO model object.
            frame: The input image/frame (BGR numpy array).
            confidence: Minimum confidence threshold.
            target_classes: List of class names to keep (e.g. ["accident"]).
                            If None or empty, all classes are returned.
            use_tracking: Whether to use model.track() for object tracking.
            tracker: Tracker config file name (e.g. "botsort.yaml").
            persist: Whether tracking IDs persist across frames.
            
        Returns:
            supervision.Detections with filtered results.
        """
        try:
            if use_tracking:
                results = model.track(
                    frame,
                    conf=confidence,
                    tracker=tracker,
                    persist=persist,
                    verbose=False,
                )
            else:
                results = model.predict(
                    frame,
                    conf=confidence,
                    verbose=False,
                )

            if not results or len(results) == 0:
                return sv.Detections.empty()

            # Convert YOLO results → supervision Detections
            detections = sv.Detections.from_ultralytics(results[0])

            # Filter by target classes if specified
            if target_classes and len(target_classes) > 0 and len(detections) > 0:
                detections = self._filter_by_class(detections, model, target_classes)

            return detections

        except Exception as e:
            self.logger.error(f"Detection failed: {e}")
            return sv.Detections.empty()

    def _filter_by_class(
        self,
        detections: sv.Detections,
        model: Any,
        target_classes: List[str],
    ) -> sv.Detections:
        """
        Keep only detections whose class name is in target_classes.
        
        Args:
            detections: Raw supervision detections.
            model: The YOLO model (used for model.names mapping).
            target_classes: Class names to keep.
            
        Returns:
            Filtered supervision.Detections.
        """
        if detections.class_id is None or len(detections) == 0:
            return detections

        # Build a set of target class IDs from names
        names = model.names  # {0: 'accident', 1: 'person', ...}
        target_ids = {
            cls_id for cls_id, cls_name in names.items()
            if cls_name.lower() in [t.lower() for t in target_classes]
        }

        if not target_ids:
            self.logger.warning(f"No matching class IDs for targets {target_classes} in model classes {list(names.values())}")
            return sv.Detections.empty()

        # Boolean mask
        mask = np.isin(detections.class_id, list(target_ids))
        return detections[mask]


if __name__ == "__main__":
    from Handlers.model_loader_handler import ModelLoaderHandler
    import cv2

    loader = ModelLoaderHandler()
    detector = ModelDetectionHandler()

    model = loader.load("AI Layer/Models/Car Accident.pt")
    if model is None:
        print("✗ Model not found")
        exit(1)

    # Create a blank test frame
    frame = np.zeros((640, 640, 3), dtype=np.uint8)
    dets = detector.detect(model, frame, confidence=0.5, target_classes=["accident"])
    print(f"✓ Detection ran — {len(dets)} detections on blank frame")
