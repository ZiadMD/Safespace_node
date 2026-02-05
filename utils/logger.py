import logging
import sys
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

class Logger:
    """Enhanced logger with console and rotating file output."""
    
    _configured = False

    @classmethod
    def setup(cls, settings: dict):
        """
        Global configuration for all Logger instances.
        
        Args:
            settings: Dictionary containing 'level', 'rotation', 'backup_count'
        """
        if cls._configured:
            return

        level_name = settings.get('level', 'INFO').upper()
        level = getattr(logging, level_name, logging.INFO)
        
        # Configure root logger to affect all modules
        root = logging.getLogger()
        root.setLevel(level)
        
        if not root.handlers:
            # Common Formatter
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

            # 1. Console Handler
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            root.addHandler(console_handler)
            
            # 2. File Handler (Rotating)
            try:
                base_dir = Path(__file__).parent.parent
                log_dir = base_dir / "logs"
                log_dir.mkdir(exist_ok=True)
                
                log_file = log_dir / "safespace.log"
                
                # Parse rotation string (e.g. "5MB" -> 5*1024*1024)
                rot_str = str(settings.get('rotation', '5MB')).upper()
                max_bytes = 5 * 1024 * 1024  # Default
                if 'MB' in rot_str:
                    try:
                        max_bytes = int(rot_str.replace('MB', '')) * 1024 * 1024
                    except ValueError: pass
                elif 'KB' in rot_str:
                    try:
                        max_bytes = int(rot_str.replace('KB', '')) * 1024
                    except ValueError: pass
                
                file_handler = RotatingFileHandler(
                    log_file, 
                    maxBytes=max_bytes,
                    backupCount=settings.get('backup_count', 5)
                )
                file_handler.setFormatter(formatter)
                root.addHandler(file_handler)
            except Exception as e:
                print(f"Failed to initialize file logger: {e}")

        cls._configured = True

    def __init__(self, name: str = "Safespace"):
        """
        Initialize logger instance.
        """
        self.logger = logging.getLogger(name)

    def info(self, message: str):
        self.logger.info(message)

    def warning(self, message: str):
        self.logger.warning(message)

    def error(self, message: str):
        self.logger.error(message)

    def debug(self, message: str):
        self.logger.debug(message)

    def critical(self, message: str):
        self.logger.critical(message)
