from typing import Optional, Dict, Any, Callable
import supervision as sv
from utils.logger import Logger
from utils.config import Config
from Handlers.Model_Loader_Handler import ModelLoader
from Handlers.Model_Detection_Handler import ModelDetectionHandler
from Handlers.Detection_Visuals_Handler import DetectionVisualsHandler
from Managers.IO_Manager import IOManager
from cv2.typing import MatLike


class AIManager:
    """Manages AI model loading, detection, and result processing."""
    
    def __init__(self, config: Config, io_manager: IOManager, 
                 on_detection: Optional[Callable[[str, sv.Detections, MatLike], None]] = None,
                 model_names: Optional[list[str]] = None):
        """
        Initialize the AI Manager.
        
        Args:
            config: Configuration object
            io_manager: IO Manager for frame access
            on_detection: Optional callback when detections occur (model_name, detections, frame)
            model_names: Optional list of specific model names to load. 
                        If None, loads all enabled models from config.
                        If a single string, it will be converted to a list.
        """
        self.config = config
        self.io_manager = io_manager
        self.logger = Logger("AIManager")
        self.on_detection = on_detection
        
        self.model_loader = ModelLoader()
        self.detection_handler = ModelDetectionHandler()
        self.visuals_handler = DetectionVisualsHandler()
        self.models: Dict[str, Dict[str, Any]] = {}
        
        # Register for frame updates
        self.io_manager.set_frame_callback(self._process_frame)
        
        # Load models based on provided names or config
        self._load_models(model_names)

        self.logger.info("AI Manager initialized")

    def _load_models(self, model_names: Optional[list[str]] = None):
        """
        Load models based on provided names or all enabled models from config.
        
        Args:
            model_names: List of model names to load, or None to load all enabled.
        """
        ai_config = self.config.get("ai", {})
        models_config = ai_config.get("models", {})
        
        if model_names is None:
            # Load all enabled models from config
            for model_name, model_conf in models_config.items():
                if model_conf.get("enabled", False):
                    self.load_model(model_name)
        else:
            # Load specific models from the provided list
            if isinstance(model_names, str):
                model_names = [model_names]
            
            for model_name in model_names:
                if model_name in models_config:
                    self.load_model(model_name)
                else:
                    self.logger.warning(f"Model '{model_name}' not found in config, skipping")

    def _load_enabled_models(self):
        """Load all models marked as enabled in config. (Deprecated: use _load_models)"""
        self._load_models(None)

    def load_model(self, model_name: str) -> Optional[Any]:
        """
        Load a model by name from configuration.
        
        Args:
            model_name: Key from config (e.g., 'accident_detection')
            
        Returns:
            Loaded model or None if failed.
        """
        ai_config = self.config.get("ai", {})
        models_config = ai_config.get("models", {})
        model_config = models_config.get(model_name)

        if not model_config:
            self.logger.error(f"No configuration found for model: {model_name}")
            return None
        
        if not model_config.get("enabled", True):
            self.logger.info(f"Model {model_name} is disabled, skipping")
            return None

        model_path = model_config.get("path")
        confidence = model_config.get("confidence", 0.5)

        if not model_path:
            self.logger.error(f"No path specified for model: {model_name}")
            return None

        self.logger.info(f"Loading model '{model_name}' from {model_path}")
        
        model = self.model_loader.load_model(model_path)
        if model is None:
            self.logger.error(f"Failed to load model: {model_name}")
            return None
            
        self.models[model_name] = {
            "model": model,
            "confidence": confidence,
            "classes": model_config.get("classes", [])
        }
        self.logger.info(f"Successfully loaded model: {model_name}")
        return model

    def unload_model(self, model_name: str) -> bool:
        """Unload a model by name."""
        model_data = self.models.pop(model_name, None)
        if model_data:
            model_path = self.config.get(f"ai.models.{model_name}.path")
            if model_path:
                self.model_loader.unload_model(model_path)
            self.logger.info(f"Unloaded model: {model_name}")
            return True
        return False

    def get_model(self, model_name: str) -> Optional[Any]:
        """Get a loaded model by name."""
        model_data = self.models.get(model_name)
        return model_data["model"] if model_data else None

    def _process_frame(self, frame: MatLike):
        """Called automatically when IO Manager has a new frame."""
        for model_name, model_data in self.models.items():
            model = model_data["model"]
            confidence = model_data["confidence"]
            
            detections = self.detection_handler.detect(model, frame, confidence)
            
            # Notify via callback if detections found
            if len(detections) > 0 and self.on_detection:
                self.on_detection(model_name, detections, frame)

    def detect(self, model_name: str, frame: MatLike) -> Optional[sv.Detections]:
        """
        Run detection on a specific frame with a named model.
        
        Args:
            model_name: Name of the model to use
            frame: Frame to process
            
        Returns:
            Detections or None if model not found
        """
        model_data = self.models.get(model_name)
        if not model_data:
            self.logger.warning(f"Model not loaded: {model_name}")
            return None
            
        return self.detection_handler.detect(
            model_data["model"], 
            frame, 
            model_data["confidence"]
        )

    def detect_and_visualize(self, model_name: str, frame: MatLike) -> tuple[Optional[sv.Detections], MatLike]:
        """
        Run detection and draw results on frame.
        
        Returns:
            Tuple of (detections, annotated_frame)
        """
        detections = self.detect(model_name, frame)
        if detections is not None and len(detections) > 0:
            frame = self.visuals_handler.visualize_detections(frame, detections)
        return detections, frame

    def process_latest(self) -> Dict[str, sv.Detections]:
        """
        Pull model - AI Manager requests latest frame and processes with all models.
        
        Returns:
            Dict mapping model names to their detections
        """
        frame = self.io_manager.get_latest_frame()
        if frame is None:
            return {}
            
        results = {}
        for model_name in self.models:
            detections = self.detect(model_name, frame)
            if detections is not None:
                results[model_name] = detections
        return results