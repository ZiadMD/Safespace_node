from typing import Optional, Dict, Any
from utils.logger import Logger
from utils.config import Config
from Handlers.Model_Loader_Handler import ModelLoader
from Handlers.Model_Detection_Handler import ModelDetectionHandler
from Managers.IO_Manager import IOManager
from cv2.typing import MatLike


class AIManager:
    def __init__(self, config: Config, io_manager: IOManager):
        self.config = config
        self.io_manager = io_manager
        self.logger = Logger("AIManager")
        
        self.model_loader = ModelLoader()
        self.detection_handler = ModelDetectionHandler()
        self.models: Dict[str, Dict[str, Any]] = {}
        
        # Register for frame updates
        self.io_manager.set_frame_callback(self._process_frame)
        
        # Load enabled models on init
        self._load_enabled_models()

    def _load_enabled_models(self):
        """Load all models marked as enabled in config."""
        models_config = self.config.get("models", {})
        for model_name, model_conf in models_config.items():
            if model_conf.get("enabled", False):
                self.load_model(model_name)

    def load_model(self, model_name: str) -> Optional[Any]:
        """
        Load a model by name from configuration.
        
        Args:
            model_name: Key from config (e.g., 'accident_detection')
            
        Returns:
            Loaded model or None if failed.
        """
        model_config = self.config.get(f"models.{model_name}")

        if not model_config:
            self.logger.error(f"No configuration found for model: {model_name}")
            return None
        
        if not model_config.get("enabled", True):
            self.logger.info(f"Model {model_name} is disabled, skipping")
            return None

        model_path = model_config.get("path")
        model_type = model_config.get("type", "yolo")
        confidence = model_config.get("confidence", 0.5)

        if not model_path:
            self.logger.error(f"No path specified for model: {model_name}")
            return None

        self.logger.info(f"Loading {model_type} model '{model_name}' from {model_path}")
        
        try:
            model = self.model_loader.load_local_model(model_path)
            self.models[model_name] = {
                "model": model,
                "type": model_type,
                "confidence": confidence
            }
            self.logger.info(f"Successfully loaded model: {model_name}")
            return model
        except Exception as e:
            self.logger.error(f"Failed to load model {model_name}: {e}")
            return None

    def get_model(self, model_name: str) -> Optional[Any]:
        """Get a loaded model by name."""
        model_data = self.models.get(model_name)
        return model_data["model"] if model_data else None

    def _process_frame(self, frame: MatLike):
        """Called automatically when IO Manager has a new frame."""
        for model_name, model_data in self.models.items():
            model = model_data["model"]
            confidence = model_data["confidence"]
            
            detections = self.detection_handler.yolo_detect(model, confidence, frame)
            # Process detections...

    def process_latest(self):
        """Pull model - AI Manager requests frames when ready."""
        frame = self.io_manager.get_latest_frame()
        if frame is not None:
            self._process_frame(frame)