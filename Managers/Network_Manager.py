"""
Network Manager - Orchestrates network communication with Central Unit.
"""
import threading
import time
from typing import Optional, Callable, Dict, Any

from Handlers.Socket_Handler import SocketHandler
from utils.logger import Logger
from utils.config import Config
from utils.constants import (DEFAULT_HEARTBEAT_INTERVAL, EVENT_HEARTBEAT)
from utils.failures import FailureManager, NetworkError


class NetworkManager:
    """Service to handle high-level network operations and lifecycle."""
    
    def __init__(self, config: Config, on_central_unit_instruction: Optional[Callable] = None):
        """
        Initialize the network manager.
        
        Args:
            config: Structured configuration object
            on_central_unit_instruction: Callback for server-sent instructions
        """
        self.config = config
        self.logger = Logger("NetworkManager")
        self.failures = FailureManager(config.get('failures', {}))
        self.on_central_unit_instruction = on_central_unit_instruction
        
        # Initialize low-level handler
        server_url = config.get('network.server_url')
        self.socket = SocketHandler(server_url, on_central_unit_update=self._on_server_update)
        
        # Background management
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.active = False

    def start(self) -> bool:
        """Start the service and establish connection."""
        self.logger.info("Connecting to Safespace Central Unit...")
        
        try:
            if not self.socket.connect():
                raise NetworkError("Initial connection failed", critical=True)
            
            self.active = True
            self._start_heartbeat()
            return True
        except NetworkError as e:
            self.failures.record_failure(e)
            return False

    def stop(self):
        """Cleanly shutdown network operations."""
        self.active = False
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=1.0)
        self.socket.disconnect()
        self.logger.info("Network Manager stopped")

    def _start_heartbeat(self):
        """Launch the background heartbeat thread."""
        def _loop():
            interval = self.config.get_int('network.heartbeat_interval', DEFAULT_HEARTBEAT_INTERVAL)
            node_id = self.config.get('node.id')
            while self.active:
                try:
                    self.socket.emit_heartbeat(node_id)
                except Exception as e:
                    self.failures.record_failure(NetworkError(f"Heartbeat failed: {e}"))
                time.sleep(interval)
        
        self.heartbeat_thread = threading.Thread(target=_loop, daemon=True)
        self.heartbeat_thread.start()

    def _on_server_update(self, data: Dict[str, Any]):
        """Internal callback for server updates."""
        if self.on_central_unit_instruction:
            self.on_central_unit_instruction(data)

    def report_accident(self, lane_number: str, media: Optional[list] = None):
        """
        Asynchronously report an accident to the server.
        
        Args:
            lane_number: The lane where the incident occurred
            media: List of media file paths
        """
        node_id = self.config.get('node.id')
        location = self.config.get('node.location', {})
        
        payload = {
            'nodeId': str(node_id),
            'lat': str(location.get('lat', '0.0')),
            'long': str(location.get('long', '0.0')),
            'laneNumber': str(lane_number)
        }
        
        self.logger.info(f"Reporting accident for lane {lane_number}...")
        
        def _report_task():
            try:
                if not self.socket.report_accident(payload, media):
                    self.failures.record_failure(NetworkError("Failed to report accident via WebSocket"))
            except Exception as e:
                self.failures.record_failure(NetworkError(f"Accident reporting error: {e}"))

        threading.Thread(target=_report_task, daemon=True).start()
