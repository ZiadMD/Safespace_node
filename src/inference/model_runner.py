"""
Model Runner — unified inference + postprocessing for YOLO and ONNX models.

Combined detection + NMS + filtering into a single detect() API.
"""
import cv2
import numpy as np
import supervision as sv
from typing import Optional, List, Any
from cv2.typing import MatLike

from core.logger import Logger


class ModelRunner:
    """Runs YOLO or ONNX inference and returns structured detections."""

    _NMS_IOU_THRESHOLD = 0.45

    def __init__(self):
        self.logger = Logger("ModelRunner")
        self._box_annotator = sv.BoxAnnotator(thickness=2)
        self._label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)

    def detect(
        self,
        model: Any,
        frame: MatLike,
        confidence: float = 0.5,
        target_classes: Optional[List[str]] = None,
        use_tracking: bool = True,
    ) -> sv.Detections:
        """
        Run inference on a frame and return filtered detections.

        Dispatches to YOLO or ONNX path based on model type.
        """
        try:
            from inference.onnx_backend import OnnxModel

            if isinstance(model, OnnxModel):
                detections = self._detect_onnx(model, frame, confidence)
            else:
                detections = self._detect_yolo(model, frame, confidence, use_tracking)

            if target_classes and len(target_classes) > 0 and len(detections) > 0:
                detections = self._filter_by_class(detections, model, target_classes)

            return detections

        except Exception as e:
            self.logger.error(f"Detection failed: {e}")
            return sv.Detections.empty()

    def annotate(self, frame: MatLike, detections: sv.Detections, model: Any) -> MatLike:
        """Draw bounding boxes and labels on a frame copy."""
        annotated = frame.copy()
        if len(detections) == 0:
            return annotated

        labels = [
            f"{model.names[c]} {conf:.2f}"
            for c, conf in zip(detections.class_id, detections.confidence)
        ]
        annotated = self._box_annotator.annotate(annotated, detections)
        annotated = self._label_annotator.annotate(annotated, detections, labels)
        return annotated

    # ── YOLO path ─────────────────────────────────────────────────

    def _detect_yolo(self, model, frame, confidence, use_tracking) -> sv.Detections:
        if use_tracking:
            results = model.track(
                frame, conf=confidence, tracker="botsort.yaml",
                persist=True, verbose=False,
            )
        else:
            results = model.predict(frame, conf=confidence, verbose=False)

        if not results or len(results) == 0:
            return sv.Detections.empty()
        return sv.Detections.from_ultralytics(results[0])

    # ── ONNX path ─────────────────────────────────────────────────

    def _detect_onnx(self, model, frame, confidence) -> sv.Detections:
        orig_h, orig_w = frame.shape[:2]
        img_h, img_w = model.input_shape

        letterboxed, ratio, (pad_w, pad_h) = self._letterbox(frame, img_h, img_w)
        blob = letterboxed[:, :, ::-1].transpose(2, 0, 1).astype(np.float32) / 255.0
        blob = np.expand_dims(blob, axis=0)
        blob = np.ascontiguousarray(blob)

        outputs = model.session.run(model.output_names, {model.input_name: blob})
        output = outputs[0]

        return self._postprocess_onnx(
            output, orig_h, orig_w, ratio, pad_w, pad_h, confidence, model.names
        )

    @staticmethod
    def _letterbox(frame, target_h, target_w, fill_value=114):
        orig_h, orig_w = frame.shape[:2]
        ratio = min(target_w / orig_w, target_h / orig_h)
        new_w, new_h = int(orig_w * ratio), int(orig_h * ratio)
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((target_h, target_w, 3), fill_value, dtype=np.uint8)
        pad_w = (target_w - new_w) // 2
        pad_h = (target_h - new_h) // 2
        canvas[pad_h: pad_h + new_h, pad_w: pad_w + new_w] = resized
        return canvas, ratio, (pad_w, pad_h)

    def _postprocess_onnx(self, output, orig_h, orig_w, ratio, pad_w, pad_h, confidence, names):
        predictions = np.squeeze(output, axis=0).T
        boxes = predictions[:, :4]
        scores = predictions[:, 4:]

        class_ids = np.argmax(scores, axis=1)
        confidences = scores[np.arange(len(scores)), class_ids]

        mask = confidences >= confidence
        boxes, class_ids, confidences = boxes[mask], class_ids[mask], confidences[mask]

        if len(boxes) == 0:
            return sv.Detections.empty()

        x1 = (boxes[:, 0] - boxes[:, 2] / 2 - pad_w) / ratio
        y1 = (boxes[:, 1] - boxes[:, 3] / 2 - pad_h) / ratio
        x2 = (boxes[:, 0] + boxes[:, 2] / 2 - pad_w) / ratio
        y2 = (boxes[:, 1] + boxes[:, 3] / 2 - pad_h) / ratio

        x1 = np.clip(x1, 0, orig_w)
        y1 = np.clip(y1, 0, orig_h)
        x2 = np.clip(x2, 0, orig_w)
        y2 = np.clip(y2, 0, orig_h)

        nms_boxes = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).tolist()
        indices = cv2.dnn.NMSBoxes(
            nms_boxes, confidences.tolist(), confidence, self._NMS_IOU_THRESHOLD
        )
        if len(indices) == 0:
            return sv.Detections.empty()

        indices = np.array(indices).flatten()
        xyxy = np.stack([x1[indices], y1[indices], x2[indices], y2[indices]], axis=1)

        return sv.Detections(
            xyxy=xyxy,
            confidence=confidences[indices],
            class_id=class_ids[indices].astype(int),
        )

    # ── Filtering ─────────────────────────────────────────────────

    def _filter_by_class(self, detections, model, target_classes):
        if detections.class_id is None or len(detections) == 0:
            return detections
        names = model.names
        target_ids = {
            cls_id for cls_id, cls_name in names.items()
            if cls_name.lower() in [t.lower() for t in target_classes]
        }
        if not target_ids:
            return sv.Detections.empty()
        mask = np.isin(detections.class_id, list(target_ids))
        return detections[mask]
