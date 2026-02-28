"""
ONNX Model — Wrapper around onnxruntime.InferenceSession for YOLOv8 ONNX models.

Provides a consistent interface with properties like .names and .input_shape
so downstream code (ModelDetection, AIManager) can work with both
YOLO (.pt) and ONNX models uniformly.
"""
import ast
from typing import Dict, List, Tuple

import onnxruntime as ort

from utils.logger import Logger


class OnnxModel:
    """
    Wraps an ONNX Runtime session for YOLOv8 model inference.

    Exposes:
        session      – the ort.InferenceSession
        names        – {class_id: class_name} dict (same format as YOLO model.names)
        input_name   – name of the input tensor
        input_shape  – (height, width) of expected input
        num_classes  – total number of classes
    """

    def __init__(self, model_path: str):
        self.logger = Logger("OnnxModel")
        self.model_path = model_path

        # Create inference session with best available provider
        providers = self._get_providers()
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.logger.info(f"ONNX session created with providers: {self.session.get_providers()}")

        # ── Input metadata ────────────────────────────────────────
        input_meta = self.session.get_inputs()[0]
        self.input_name: str = input_meta.name
        self._input_shape = input_meta.shape          # e.g. [1, 3, 640, 640]
        self.img_height: int = int(self._input_shape[2])
        self.img_width: int = int(self._input_shape[3])

        # ── Output metadata ───────────────────────────────────────
        self.output_names: List[str] = [o.name for o in self.session.get_outputs()]

        # ── Class names ───────────────────────────────────────────
        self.names: Dict[int, str] = self._extract_names()

        self.logger.info(
            f"ONNX model ready: input={self.img_width}x{self.img_height}, "
            f"classes={len(self.names)}, names={list(self.names.values())}"
        )

    # ── Provider selection ────────────────────────────────────────

    @staticmethod
    def _get_providers() -> List[str]:
        """Pick GPU provider if available, always fall back to CPU."""
        available = ort.get_available_providers()
        providers: List[str] = []
        if "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
        return providers

    # ── Metadata extraction ───────────────────────────────────────

    def _extract_names(self) -> Dict[int, str]:
        """
        Extract class names from ONNX model metadata.

        Ultralytics exports embed names as a Python dict literal string
        in the custom metadata under the key ``names``.
        Falls back to generic ``class_<id>`` labels when metadata is absent.
        """
        metadata = self.session.get_modelmeta().custom_metadata_map

        if "names" in metadata:
            try:
                parsed = ast.literal_eval(metadata["names"])
                if isinstance(parsed, dict):
                    return {int(k): str(v) for k, v in parsed.items()}
            except (ValueError, SyntaxError):
                self.logger.warning("Failed to parse class names from ONNX metadata")

        # Fallback: infer class count from output shape
        # YOLOv8 output is [1, 4+nc, N] where 4 = box coords
        output_shape = self.session.get_outputs()[0].shape
        if output_shape and len(output_shape) == 3:
            dim1, dim2 = output_shape[1], output_shape[2]
            # The smaller non-batch dim is (4 + nc)
            box_dim = min(dim1, dim2)
            nc = max(box_dim - 4, 1)
            self.logger.warning(
                f"No class names in metadata — generating {nc} generic labels"
            )
            return {i: f"class_{i}" for i in range(nc)}

        return {}

    # ── Properties ────────────────────────────────────────────────

    @property
    def input_shape(self) -> Tuple[int, int]:
        """Returns (height, width) of the model input."""
        return (self.img_height, self.img_width)

    @property
    def num_classes(self) -> int:
        return len(self.names)
