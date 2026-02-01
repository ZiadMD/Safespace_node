from ultralytics import YOLO
from inference import get_model
from utils.constants import ROBOFLOW_API_KEY
from utils.logger import Logger
from utils.config import Config


class ModelLoader:

    def __init__(self):
        self.logger = Logger.get_logger("ModelLoader")
        self.config = Config

    def load_model(self, model_name: str):
        """
        Load a model based on the configuration.

        Args:
            model_name (str): Name of the model to load (e.g., 'accident_detection_local', 'accident_detection_roboflow')
        Returns:
            Loaded model object or None if loading fails.
        """
        model_config = self.config.get(f"ai.{model_name}")
        if not model_config:
            self.logger.error(f"No configuration found for model: {model_name}")
            return None

        model_path = model_config.get("model_path")
        model_id = model_config.get("model_id")

        if model_id:
            return self.load_roboflow_model(model_id)
        elif model_path:
            return self.load_local_model(model_path)
        else:
            self.logger.error(f"No valid model path or ID provided for model: {model_name}")
            return None

    def load_local_model(self, model_path: str) -> YOLO:
        """
        Load a local model from the specified path.
        
        Args:
            model_path (str): Path to the local model file.
        Returns:
            Loaded model object or None if loading fails.
        """
        try:
            print(f"Loading local model from: {model_path}...")
            model = YOLO(model_path)
            print("Model loaded successfully!")
            return model
        except Exception as e:
            print(f"Error loading local model: {e}")
            return None
    
    def load_roboflow_model(self, model_id: str) -> Model:
        """
        Load a model from Roboflow Inference using the provided model ID.

        Args:
            model_id (str): Roboflow model ID (e.g., 'project-name/version')
        Returns:
            Loaded model object or None if loading fails.
        """
        print(f"Loading Roboflow model: {model_id}...")
        try:
            model = get_model(model_id=model_id, api_key=ROBOFLOW_API_KEY)
            print("Roboflow model loaded successfully!")
            return model
        except Exception as e:
            print(f"Error loading Roboflow model: {e}")
            return None

