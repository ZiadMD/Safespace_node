"""
Structured error handling and failure tracking for Safespace Node.
"""
import time
from typing import Dict, List, Optional
from utils.logger import Logger

class SafespaceError(Exception):
    """Base class for all Safespace exceptions."""
    def __init__(self, message: str, critical: bool = False):
        super().__init__(message)
        self.message = message
        self.critical = critical
        self.timestamp = time.time()

class NetworkError(SafespaceError):
    """Exception raised for network-related failures."""
    pass

class ConfigError(SafespaceError):
    """Exception raised for configuration-related failures."""
    pass

class DisplayError(SafespaceError):
    """Exception raised for GUI-related failures."""
    pass

class FailureManager:
    """Tracks and manages recurring failures to improve system resilience."""
    
    def __init__(self, settings: Optional[dict] = None):
        """
        Initialize the failure manager.
        
        Args:
            settings: Dictionary containing failure thresholds (from failures.json)
        """
        self.logger = Logger("FailureManager")
        
        # Default fallback settings
        self.settings = settings or {}
        self.threshold = self.settings.get('threshold', 5)
        self.window_seconds = self.settings.get('window_seconds', 300)
        
        self.failures: Dict[str, List[float]] = {}
        self.history: List[SafespaceError] = []

    def record_failure(self, error: Exception):
        """
        Record a failure incident.
        
        Args:
            error: The exception that occurred.
        """
        error_type = type(error).__name__
        now = time.time()
        
        if error_type not in self.failures:
            self.failures[error_type] = []
            
        self.failures[error_type].append(now)
        
        # Log the failure
        if isinstance(error, SafespaceError):
            self.history.append(error)
            msg = f"Failure detected: {error_type} - {error.message}"
            if error.critical:
                self.logger.error(f"CRITICAL: {msg}")
            else:
                self.logger.warning(msg)
        else:
            self.logger.error(f"Unexpected failure: {error_type} - {str(error)}")

        # Check if threshold exceeded
        if self.is_threshold_exceeded(error_type):
            self.logger.warning(f"Resilience Alert: Failure '{error_type}' exceeded threshold ({self.threshold} in {self.window_seconds}s).")

    def is_threshold_exceeded(self, error_type: str) -> bool:
        """Check if a specific error type has exceeded the frequency threshold."""
        if error_type not in self.failures:
            return False
            
        now = time.time()
        # Clean old failures
        self.failures[error_type] = [t for t in self.failures[error_type] if (now - t) < self.window_seconds]
        
        return len(self.failures[error_type]) >= self.threshold

    def get_recent_history(self, count: int = 10) -> List[SafespaceError]:
        """Return the most recent failures."""
        return self.history[-count:]

    def clear(self):
        """Reset all tracked failures."""
        self.failures = {}
        self.history = []
        self.logger.info("Failure history cleared.")
