"""
Model Detection — Runs inference on a single frame using a loaded YOLO or ONNX model.

Responsible only for:
  - Running model.track() / model.predict() on a frame (YOLO path)
  - Running ONNX Runtime session with preprocessing + NMS (ONNX path)
  - Converting raw results into supervision Detections
  - Filtering detections by target classes and confidence
"""
import cv2
import numpy as np
import supervision as sv
from typing import Optional, List, Any
from cv2.typing import MatLike

from utils.logger import Logger


class ModelDetection:
    """Runs YOLO or ONNX inference and returns structured detections."""

    _NMS_IOU_THRESHOLD = 0.45  # IOU threshold for NMS (ONNX path)

    def __init__(self):
        self.logger = Logger("ModelDetection")

    # ── Public API ────────────────────────────────────────────────

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

        Automatically dispatches to the YOLO or ONNX inference path
        based on the model type.

        Args:
            model: A loaded YOLO model or OnnxModel object.
            frame: The input image/frame (BGR numpy array).
            confidence: Minimum confidence threshold.
            target_classes: List of class names to keep (e.g. ["accident"]).
                            If None or empty, all classes are returned.
            use_tracking: Whether to use model.track() for object tracking
                          (YOLO only — ignored for ONNX models).
            tracker: Tracker config file name (e.g. "botsort.yaml").
            persist: Whether tracking IDs persist across frames.

        Returns:
            supervision.Detections with filtered results.
        """
        try:
            from handlers.onnx_model import OnnxModel

            if isinstance(model, OnnxModel):
                detections = self._detect_onnx(model, frame, confidence)
            else:
                detections = self._detect_yolo(
                    model, frame, confidence, use_tracking, tracker, persist
                )

            # Filter by target classes (works for both — both expose .names)
            if target_classes and len(target_classes) > 0 and len(detections) > 0:
                detections = self._filter_by_class(detections, model, target_classes)

            return detections

        except Exception as e:
            self.logger.error(f"Detection failed: {e}")
            return sv.Detections.empty()

    # ── YOLO inference path ───────────────────────────────────────

    def _detect_yolo(
        self,
        model: Any,
        frame: MatLike,
        confidence: float,
        use_tracking: bool,
        tracker: str,
        persist: bool,
    ) -> sv.Detections:
        """Run YOLO .pt inference via Ultralytics."""
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

        return sv.Detections.from_ultralytics(results[0])

    # ── ONNX inference path ───────────────────────────────────────

    def _detect_onnx(
        self,
        model: Any,
        frame: MatLike,
        confidence: float,
    ) -> sv.Detections:
        """
        Run ONNX Runtime inference on a frame.

        Pipeline: letterbox → normalize → CHW → session.run → postprocess + NMS
        """
        orig_h, orig_w = frame.shape[:2]
        img_h, img_w = model.input_shape  # (height, width)

        # ── Preprocessing ─────────────────────────────────────────
        letterboxed, ratio, (pad_w, pad_h) = self._letterbox(
            frame, img_h, img_w
        )

        # BGR → RGB, HWC → CHW, float32 [0, 1], add batch dim
        blob = letterboxed[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, axis=0)
        blob = np.ascontiguousarray(blob)

        # ── Inference ─────────────────────────────────────────────
        outputs = model.session.run(model.output_names, {model.input_name: blob})
        output = outputs[0]  # Expected shape: [1, 4+nc, N]

        # ── Postprocessing ────────────────────────────────────────
        return self._postprocess_onnx(
            output,
            orig_h, orig_w,
            ratio, pad_w, pad_h,
            confidence,
            model.names,
        )

    # ── ONNX helpers ──────────────────────────────────────────────

    @staticmethod
    def _letterbox(
        frame: MatLike,
        target_h: int,
        target_w: int,
        fill_value: int = 114,
    ):
        """
        Resize *frame* with letterboxing to ``(target_h, target_w)``.

        Returns:
            (letterboxed_image, scale_ratio, (pad_w, pad_h))
        """
        orig_h, orig_w = frame.shape[:2]

        ratio = min(target_w / orig_w, target_h / orig_h)
        new_w = int(orig_w * ratio)
        new_h = int(orig_h * ratio)

        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)

        canvas = np.full((target_h, target_w, 3), fill_value, dtype=np.uint8)
        pad_w = (target_w - new_w) // 2
        pad_h = (target_h - new_h) // 2
        canvas[pad_h : pad_h + new_h, pad_w : pad_w + new_w] = resized

        return canvas, ratio, (pad_w, pad_h)

    def _postprocess_onnx(
        self,
        output: np.ndarray,
        orig_h: int,
        orig_w: int,
        ratio: float,
        pad_w: int,
        pad_h: int,
        confidence: float,
        names: dict,
    ) -> sv.Detections:
        """
        Parse YOLOv8 ONNX output tensor into ``sv.Detections``.

        YOLOv8 output shape: ``[1, 4+nc, N]``
            - 4 = box centre-x, centre-y, width, height
            - nc = number of classes
            - N = number of candidate detections
        """
        # Squeeze batch dim and transpose: [4+nc, N] → [N, 4+nc]
        predictions = np.squeeze(output, axis=0).T

        # Split boxes  vs  class scores
        boxes = predictions[:, :4]       # cx, cy, w, h  (in letterboxed coords)
        scores = predictions[:, 4:]      # per-class confidence

        # Best class per prediction
        class_ids = np.argmax(scores, axis=1)
        confidences = scores[np.arange(len(scores)), class_ids]

        # Confidence filter
        mask = confidences >= confidence
        boxes = boxes[mask]
        class_ids = class_ids[mask]
        confidences = confidences[mask]

        if len(boxes) == 0:
            return sv.Detections.empty()

        # cx, cy, w, h  →  x1, y1, x2, y2  (still in letterboxed coords)
        x1 = boxes[:, 0] - boxes[:, 2] / 2
        y1 = boxes[:, 1] - boxes[:, 3] / 2
        x2 = boxes[:, 0] + boxes[:, 2] / 2
        y2 = boxes[:, 1] + boxes[:, 3] / 2

        # Remove letterbox padding and scale back to original image
        x1 = (x1 - pad_w) / ratio
        y1 = (y1 - pad_h) / ratio
        x2 = (x2 - pad_w) / ratio
        y2 = (y2 - pad_h) / ratio

        # Clip to image bounds
        x1 = np.clip(x1, 0, orig_w)
        y1 = np.clip(y1, 0, orig_h)
        x2 = np.clip(x2, 0, orig_w)
        y2 = np.clip(y2, 0, orig_h)

        # ── NMS ───────────────────────────────────────────────────
        # cv2.dnn.NMSBoxes expects [x, y, w, h] (top-left origin)
        nms_boxes = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).tolist()
        indices = cv2.dnn.NMSBoxes(
            nms_boxes,
            confidences.tolist(),
            confidence,
            self._NMS_IOU_THRESHOLD,
        )

        if len(indices) == 0:
            return sv.Detections.empty()

        indices = np.array(indices).flatten()

        xyxy = np.stack(
            [x1[indices], y1[indices], x2[indices], y2[indices]], axis=1
        )

        return sv.Detections(
            xyxy=xyxy,
            confidence=confidences[indices],
            class_id=class_ids[indices].astype(int),
        )

    # ── Shared filtering ──────────────────────────────────────────

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
            self.logger.warning(
                f"No matching class IDs for targets {target_classes} "
                f"in model classes {list(names.values())}"
            )
            return sv.Detections.empty()

        # Boolean mask
        mask = np.isin(detections.class_id, list(target_ids))
        return detections[mask]
