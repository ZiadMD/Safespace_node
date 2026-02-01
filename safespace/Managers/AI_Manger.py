from utils.logger import Logger
from utils.config import Config
from Handlers.Model_Loader_Handler import ModelLoader

class AIManager:
    def __init__(self, config: Config):
        self.logger = Logger.get_logger("AIManager")
        self.config = config
        self.model_loader = ModelLoader()
        self.models = {}
    
    def load_model(self, model_name: str):
        model_config = self.config.get(f"ai.{model_name}")

        if not model_config:
            self.logger.error(f"No configuration found for model: {model_name}")
            return None
        
        model_path = model_config.get("model_path")
        model_id = model_config.get("model_id")

        if model_path:
            self.logger.info(f"Loading local model for {model_name} from {model_path}")
            model = self.model_loader.load_local_model(model_path)
            self.models[model_name] = {model_name: model, "type": "local"}
            return model
        elif model_id:
            self.logger.info(f"Loading Roboflow model for {model_name} with ID {model_id}")
            model = self.model_loader.load_roboflow_model(model_id)
            self.models[model_name] = {model_name: model, "type": "roboflow"}
            return model
        else:
            self.logger.error(f"No valid model source specified for {model_name}")
            return None
    
    
    