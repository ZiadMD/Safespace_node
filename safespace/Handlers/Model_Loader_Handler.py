from ultralytics import YOLO
from inference import get_model
from inference.core.models.base import Model
from utils.constants import ROBOFLOW_API_KEY
from utils.logger import Logger
from utils.config import Config


class ModelLoader:

    def __init__(self):
        self.logger = Logger.get_logger("ModelLoader")

    def load_local_model(self, model_path: str) -> YOLO:
        """
        Load a local model from the specified path.
        
        Args:
            model_path (str): Path to the local model file.
        Returns:
            Loaded model object or None if loading fails.
        """
        try:
            model = YOLO(model_path)
            self.logger.info("Local model loaded successfully!")
            return model
        except Exception as e:
            self.logger.error(f"Error loading local model: {e}")
            return None
    
    def load_roboflow_model(self, model_id: str) -> Model:
        """
        Load a model from Roboflow Inference using the provided model ID.

        Args:
            model_id (str): Roboflow model ID (e.g., 'project-name/version')
        Returns:
            Loaded model object or None if loading fails.
        """
        self.logger.info(f"Loading Roboflow model with ID: {model_id}")
        try:
            model = get_model(model_id=model_id, api_key=ROBOFLOW_API_KEY)
            self.logger.info("Roboflow model loaded successfully!")
            return model
        except Exception as e:
            self.logger.error(f"Error loading Roboflow model: {e}")
            return None

