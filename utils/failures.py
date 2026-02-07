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
        self._max_history = 100  # Cap to prevent unbounded memory growth
        self._lock = __import__('threading').Lock()

    def record_failure(self, error: Exception):
        """
        Record a failure incident (thread-safe).
        
        Args:
            error: The exception that occurred.
        """
        with self._lock:
            error_type = type(error).__name__
            now = time.time()
            
            if error_type not in self.failures:
                self.failures[error_type] = []
                
            self.failures[error_type].append(now)
            
            # Prune old entries beyond the time window
            cutoff = now - self.window_seconds
            self.failures[error_type] = [
                t for t in self.failures[error_type] if t > cutoff
            ]
            
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

            # Cap history to prevent memory leak
            if len(self.history) > self._max_history:
                self.history = self.history[-self._max_history:]

            # Check if threshold exceeded
            if len(self.failures.get(error_type, [])) >= self.threshold:
                self.logger.warning(
                    f"Resilience Alert: '{error_type}' exceeded threshold "
                    f"({self.threshold} in {self.window_seconds}s)"
                )

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
