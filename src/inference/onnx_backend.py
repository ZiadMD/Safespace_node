"""
ONNX Backend — Wrapper around onnxruntime.InferenceSession for YOLOv8 ONNX models.

Provides .names and .input_shape so downstream code works uniformly
with both YOLO (.pt) and ONNX models.
"""
import ast
from typing import Dict, List, Tuple

import onnxruntime as ort

from core.logger import Logger


class OnnxModel:
    """
    Wraps an ONNX Runtime session for YOLOv8 inference.

    Exposes:
        session      – the ort.InferenceSession
        names        – {class_id: class_name} dict
        input_name   – name of the input tensor
        input_shape  – (height, width) of expected input
    """

    def __init__(self, model_path: str):
        self.logger = Logger("OnnxModel")
        self.model_path = model_path

        providers = self._get_providers()
        self.session = ort.InferenceSession(model_path, providers=providers)
        self.logger.info(f"ONNX session: providers={self.session.get_providers()}")

        input_meta = self.session.get_inputs()[0]
        self.input_name: str = input_meta.name
        self._input_shape = input_meta.shape
        self.img_height: int = int(self._input_shape[2])
        self.img_width: int = int(self._input_shape[3])

        self.output_names: List[str] = [o.name for o in self.session.get_outputs()]
        self.names: Dict[int, str] = self._extract_names()

        self.logger.info(
            f"ONNX model ready: {self.img_width}x{self.img_height}, "
            f"classes={list(self.names.values())}"
        )

    @staticmethod
    def _get_providers() -> List[str]:
        available = ort.get_available_providers()
        providers = []
        if "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
        return providers

    def _extract_names(self) -> Dict[int, str]:
        metadata = self.session.get_modelmeta().custom_metadata_map
        if "names" in metadata:
            try:
                parsed = ast.literal_eval(metadata["names"])
                if isinstance(parsed, dict):
                    return {int(k): str(v) for k, v in parsed.items()}
            except (ValueError, SyntaxError):
                pass

        output_shape = self.session.get_outputs()[0].shape
        if output_shape and len(output_shape) == 3:
            dim1, dim2 = output_shape[1], output_shape[2]
            box_dim = min(dim1, dim2)
            nc = max(box_dim - 4, 1)
            return {i: f"class_{i}" for i in range(nc)}
        return {}

    @property
    def input_shape(self) -> Tuple[int, int]:
        return (self.img_height, self.img_width)

    @property
    def num_classes(self) -> int:
        return len(self.names)
