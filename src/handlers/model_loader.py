"""Model Loader — Loads and manages YOLO / ONNX models from disk.

Responsible only for:
  - Loading a model file into memory (.pt via Ultralytics, .onnx via OnnxModel)
  - Holding references to loaded models
  - Unloading models to free resources
"""
from typing import Optional, Dict, Any
from pathlib import Path

from utils.logger import Logger


class ModelLoader:
    """Loads and caches YOLO (.pt) and ONNX (.onnx) models."""

    def __init__(self):
        self.logger = Logger("ModelLoader")
        self._models: Dict[str, Any] = {}  # path -> model object

    def load(self, model_path: str) -> Optional[Any]:
        """
        Load a model from disk.  Auto-detects format by file extension.

        Supported formats:
            .pt   → loaded via ``ultralytics.YOLO``
            .onnx → loaded via ``handlers.onnx_model.OnnxModel``

        Args:
            model_path: Path to the model file.

        Returns:
            The loaded model object, or None on failure.
        """
        # Return cached model if already loaded
        if model_path in self._models:
            self.logger.debug(f"Model already loaded: {model_path}")
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
        """Load a YOLO .pt model via Ultralytics."""
        try:
            from ultralytics import YOLO
            model = YOLO(str(path))
            self._models[model_path] = model
            self.logger.info(f"YOLO model loaded: {path.name}")
            return model
        except Exception as e:
            self.logger.error(f"Failed to load YOLO model '{model_path}': {e}")
            return None

    def _load_onnx(self, model_path: str, path: Path) -> Optional[Any]:
        """Load an ONNX model via OnnxModel wrapper (onnxruntime)."""
        try:
            from handlers.onnx_model import OnnxModel
            model = OnnxModel(str(path))
            self._models[model_path] = model
            self.logger.info(f"ONNX model loaded: {path.name}")
            return model
        except Exception as e:
            self.logger.error(f"Failed to load ONNX model '{model_path}': {e}")
            return None

    def unload(self, model_path: str) -> bool:
        """
        Remove a model from cache to free memory.

        Returns:
            True if the model was found and removed.
        """
        if model_path in self._models:
            del self._models[model_path]
            self.logger.info(f"Model unloaded: {model_path}")
            return True
        return False

    def unload_all(self):
        """Unload all cached models."""
        count = len(self._models)
        self._models.clear()
        self.logger.info(f"All models unloaded ({count})")

    def get(self, model_path: str) -> Optional[Any]:
        """Get a previously loaded model by path."""
        return self._models.get(model_path)

    @property
    def loaded_models(self) -> list:
        """List of currently loaded model paths."""
        return list(self._models.keys())
