"""Configuration management for Safespace Node."""
import yaml
import os
import re
from pathlib import Path
from typing import Any


class Config:
    """Configuration manager that loads from a single YAML file."""
    
    def __init__(self, config_file: str = None):
        """
        Initialize configuration by loading a single YAML config file.
        
        Args:
            config_file: Path to YAML config file (defaults to configs/config.yaml)
        """
        self.config = {}
        
        # Determine config file path
        if not config_file:
            base_dir = Path(__file__).parent.parent.parent
            config_file = base_dir / "configs" / "config.yaml"
        else:
            config_file = Path(config_file)

        # Remember the source path so values can be persisted back later.
        self._config_file = str(config_file)

        # Load YAML config
        if config_file.exists():
            self._load_from_file(config_file)
        else:
            raise FileNotFoundError(f"Config file not found: {config_file}")
        
        # Override from environment variables if present
        self._load_from_env()

    def _load_from_env(self):
        """Override configuration from environment variables."""
        env_overrides = {
            'NODE_ID': 'node.id',
            'SERVER_URL': 'network.server_url',
            'LOG_LEVEL': 'logging.level',
        }
        for env_var, config_key in env_overrides.items():
            value = os.environ.get(env_var)
            if value:
                self._set_nested(config_key, value)

    def _set_nested(self, key: str, value: Any):
        """Set a nested config value using dot notation."""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def _load_from_file(self, path: Path):
        """Load configuration from YAML file."""
        try:
            with open(path, 'r') as f:
                loaded = yaml.safe_load(f)
                if loaded and isinstance(loaded, dict):
                    self.config = loaded
                else:
                    raise ValueError(f"Invalid or empty config: {path}")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {path}: {e}")

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
        """Save current configuration to YAML file."""
        try:
            with open(path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False)
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to save config to {path}: {e}")

    def update_location(self, lat, long) -> bool:
        """
        Persist the latest GPS fix to node.location (in memory and on disk),
        so a later GPS dropout falls back to the last known location.

        Uses a targeted line edit so the YAML file's comments and formatting
        are preserved (unlike save_to_file, which would rewrite the whole file
        via yaml.dump and drop every comment). Returns True if the file was
        updated.
        """
        # Update the in-memory config immediately.
        self._set_nested("node.location.lat", lat)
        self._set_nested("node.location.long", long)

        if not self._config_file or not os.path.exists(self._config_file):
            return False

        def _replace(line: str, key: str, value) -> str:
            # Preserve indentation and any trailing inline comment; replace
            # only the value (quoted, to match the existing config style).
            m = re.match(
                rf"^(\s+{key}:\s*)(?:\"[^\"]*\"|'[^']*'|\S+)?(\s*#.*)?(\r?\n?)$",
                line,
            )
            if not m:
                return line
            indent, comment, newline = m.group(1), m.group(2) or "", m.group(3) or "\n"
            return f'{indent}"{value}"{comment}{newline}'

        try:
            with open(self._config_file, "r") as f:
                lines = f.readlines()

            changed = False
            for i, line in enumerate(lines):
                if re.match(r"^\s{4}lat:\s", line):
                    new = _replace(line, "lat", lat)
                elif re.match(r"^\s{4}long:\s", line):
                    new = _replace(line, "long", long)
                else:
                    continue
                if new != line:
                    lines[i] = new
                    changed = True

            if changed:
                with open(self._config_file, "w") as f:
                    f.writelines(lines)
            return changed
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"Failed to persist GPS location to {self._config_file}: {e}"
            )
            return False


if __name__ == "__main__":
    # Test stub
    config = Config()
    print(f"Node ID: {config.get('node.id')}")
    print(f"Camera width: {config.get('camera.resolution.width')}")
    print(f"Server URL: {config.get('network.server_url')}")
