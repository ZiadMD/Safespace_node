"""
Model Loader — Loads YOLO (.pt) and ONNX (.onnx) models from disk.

Auto-detects format by file extension.
"""
from typing import Optional, Dict, Any
from pathlib import Path

from core.logger import Logger


class ModelLoader:
    """Loads and caches YOLO (.pt) and ONNX (.onnx) models."""

    def __init__(self):
        self.logger = Logger("ModelLoader")
        self._models: Dict[str, Any] = {}

    def load(self, model_path: str) -> Optional[Any]:
        """
        Load a model from disk. Auto-detects format by extension.

        Returns the loaded model object, or None on failure.
        """
        if model_path in self._models:
            return self._models[model_path]

        path = Path(model_path)
        if not path.exists():
            self.logger.error(f"Model file not found: {model_path}")
            return None

        suffix = path.suffix.lower()
        if suffix == ".onnx":
            return self._load_onnx(model_path, path)
        else:
            return self._load_yolo(model_path, path)

    def _load_yolo(self, model_path: str, path: Path) -> Optional[Any]:
        try:
            from ultralytics import YOLO
            model = YOLO(str(path))
            self._models[model_path] = model
            self.logger.info(f"YOLO model loaded: {path.name}")
            return model
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model: {e}")
            return None

    def _load_onnx(self, model_path: str, path: Path) -> Optional[Any]:
        try:
            from inference.onnx_backend import OnnxModel
            model = OnnxModel(str(path))
            self._models[model_path] = model
            self.logger.info(f"ONNX model loaded: {path.name}")
            return model
        except Exception as e:
            self.logger.error(f"Failed to load ONNX model: {e}")
            return None

    def unload_all(self):
        count = len(self._models)
        self._models.clear()
        self.logger.info(f"All models unloaded ({count})")

    @property
    def loaded_models(self) -> list:
        return list(self._models.keys())
