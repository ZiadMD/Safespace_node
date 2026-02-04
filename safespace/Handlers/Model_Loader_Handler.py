from ultralytics import YOLO
import torch
from pathlib import Path
from utils.logger import Logger


class ModelLoader:
    """Handler for loading and caching YOLO models with GPU/CPU optimization."""

    def __init__(self):
        self.logger = Logger.get_logger("ModelLoader")
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model_cache = {}

    def load_model(self, model_path: str) -> YOLO:
        """
        Load a YOLO model from the specified path with caching.
        
        Args:
            model_path (str): Path to the local model file.
            
        Returns:
            YOLO: Loaded model object or None if loading fails.
        """
        # Check cache first
        if model_path in self.model_cache:
            self.logger.info(f"Using cached model: {model_path}")
            return self.model_cache[model_path]
        
        # Validate path exists
        if not Path(model_path).exists():
            self.logger.error(f"Model file not found: {model_path}")
            return None
        
        try:
            model = YOLO(model_path)
            model.to(self.device)
            self.model_cache[model_path] = model
            self.logger.info(f"Model loaded successfully on {self.device}: {model_path}")
            return model
        except Exception as e:
            self.logger.error(f"Error loading model: {e}")
            return None

    def unload_model(self, model_path: str) -> bool:
        """Remove model from cache to free memory."""
        if model_path in self.model_cache:
            del self.model_cache[model_path]
            self.logger.info(f"Model unloaded from cache: {model_path}")
            return True
        return False