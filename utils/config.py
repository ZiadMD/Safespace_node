"""
Configuration management for Safespace Node.
"""
import json
import os
from pathlib import Path
from typing import Dict, Any


class Config:
    """Configuration manager that merges multiple domain-specific JSON files."""
    
    def __init__(self, configs_dir: str = None):
        """
        Initialize configuration by loading all JSON files in the configs directory.
        
        Args:
            configs_dir: Path to directory containing JSON configs (defaults to safespace/configs)
        """
        self.config = {}
        
        # Determine configs directory
        if not configs_dir:
            base_dir = Path(__file__).parent.parent
            configs_dir = base_dir / "configs"
        else:
            configs_dir = Path(configs_dir)

        # 1. Load all JSON files if directory exists
        if configs_dir.exists() and configs_dir.is_dir():
            for config_file in sorted(configs_dir.glob("*.json")):
                self.load_from_file(str(config_file))
        
        # 2. Override from environment variables if present
        self._load_from_env()

    def _load_from_env(self):
        """Load configuration from environment variables."""
        if os.environ.get('NODE_ID'):
            self.config.setdefault('node', {})['id'] = os.environ.get('NODE_ID')
        if os.environ.get('SERVER_URL'):
            self.config.setdefault('network', {})['server_url'] = os.environ.get('SERVER_URL')

    def load_from_file(self, path: str):
        """Load configuration from JSON file."""
        try:
            with open(path, 'r') as f:
                user_config = json.load(f)
                self._merge_config(user_config)
        except Exception as e:
            print(f"Failed to load config from {path}: {e}")

    def _merge_config(self, user_config: Dict[str, Any]):
        """Merge user config with defaults recursively."""
        def update(d, u):
            for k, v in u.items():
                if isinstance(v, dict):
                    d[k] = update(d.get(k, {}), v)
                else:
                    d[k] = v
            return d
        
        update(self.config, user_config)

    def get_int(self, key: str, default: int = 0) -> int:
        """Get config value as integer."""
        val = self.get(key, default)
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get config value as float."""
        val = self.get(key, default)
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get config value as boolean."""
        val = self.get(key, default)
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ('true', '1', 'yes', 'on')
        return bool(val)

    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value."""
        keys = key.split('.')
        value = self.config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
                
        return value

    def save_to_file(self, path: str):
        """Save current configuration to file."""
        try:
            with open(path, 'w') as f:
                json.dump(self.config, f, indent=2)
        except Exception as e:
            print(f"Failed to save config to {path}: {e}")


if __name__ == "__main__":
    # Test stub
    config = Config()
    print(f"Camera width: {config.get('camera.width')}")
    print(f"Server URL: {config.get('network.server_url')}")
    print(f"Lane count: {config.get('lanes.count')}")
