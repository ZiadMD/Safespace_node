"""
Model Loader Handler - Loads and manages YOLO models from disk.

Responsible only for:
  - Loading a model file into memory
  - Holding references to loaded models
  - Unloading models to free resources
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from typing import Optional, Dict, Any
from utils.logger import Logger


class ModelLoaderHandler:
    """Loads and caches YOLO models."""

    def __init__(self):
        self.logger = Logger("ModelLoader")
        self._models: Dict[str, Any] = {}  # path -> model object

    def load(self, model_path: str) -> Optional[Any]:
        """
        Load a YOLO model from disk.
        
        Args:
            model_path: Path to the .pt model file.
            
        Returns:
            The loaded YOLO model, or None on failure.
        """
        # Return cached model if already loaded
        if model_path in self._models:
            self.logger.debug(f"Model already loaded: {model_path}")
            return self._models[model_path]

        path = Path(model_path)
        if not path.exists():
            self.logger.error(f"Model file not found: {model_path}")
            return None

        try:
            from ultralytics import YOLO
            model = YOLO(str(path))
            self._models[model_path] = model
            self.logger.info(f"Model loaded: {path.name}")
            return model
        except Exception as e:
            self.logger.error(f"Failed to load model '{model_path}': {e}")
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


if __name__ == "__main__":
    loader = ModelLoaderHandler()
    
    test_path = "AI Layer/Models/Car Accident.pt"
    model = loader.load(test_path)
    
    if model:
        print(f"✓ Model loaded: {test_path}")
        print(f"  Class names: {model.names}")
        print(f"  Loaded models: {loader.loaded_models}")
    else:
        print(f"✗ Failed to load: {test_path}")
