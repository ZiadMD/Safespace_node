"""
Socket Handler - Low-level network communication with Central Unit.

Implements the Reporter protocol. Uses Socket.IO for real-time events
and HTTP POST for accident report uploads with media attachments.
Includes reconnection logic with exponential backoff.
"""
import socketio
import requests
import os
import time
import mimetypes
from typing import Optional, Dict, Any, Callable
from utils.logger import Logger
from utils.constants import (EVENT_ROAD_UPDATE, EVENT_CENTRAL_UNIT_UPDATE, 
                             EVENT_HEARTBEAT, EVENT_ACCIDENT_REPORT)


class SocketHandler:
    """Handles low-level network communication (WebSockets and HTTP POST).
    
    Implements the Reporter protocol:
        report(payload, media_paths) -> bool
        connect() -> bool
        disconnect() -> None
        emit_heartbeat(node_id) -> None
    """
    
    def __init__(self, server_url: str, on_central_unit_update: Optional[Callable] = None):
        """
        Initialize socket handler.
        
        Args:
            server_url: URL of the Central Unit server
            on_central_unit_update: Callback for updates from the Central Unit
        """
        self.server_url = server_url
        self.sio = socketio.Client(reconnection=True, reconnection_attempts=10,
                                   reconnection_delay=2, reconnection_delay_max=30)
        self.connected = False
        self.on_central_unit_update = on_central_unit_update
        self.logger = Logger("SocketHandler")
        
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup socket.io event handlers."""
        @self.sio.on('connect')
        def on_connect():
            self.connected = True
            transport = "unknown"
            try:
                transport = self.sio.eio.transport
            except Exception:
                pass
            self.logger.info(f"Connected to Central Unit at {self.server_url} (Transport: {transport})")

        @self.sio.on('disconnect')
        def on_disconnect():
            self.connected = False
            self.logger.warning("Disconnected from Central Unit")

        @self.sio.on('*')
        def catch_all(event, data):
            self.logger.debug(f"Socket Event Received: '{event}' | Data: {data}")
            if event in (EVENT_ROAD_UPDATE, EVENT_CENTRAL_UNIT_UPDATE, "admin_accident_response"):
                if self.on_central_unit_update:
                    self.on_central_unit_update(data)

    def connect(self) -> bool:
        """Connect to the Central Unit server."""
        if self.connected:
            return True
            
        try:
            self.sio.connect(self.server_url)
            return True
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False

    def disconnect(self) -> None:
        """Disconnect from the server."""
        if self.connected:
            try:
                self.sio.disconnect()
            except Exception:
                pass

    def report(self, payload: Dict[str, Any], media_paths: Optional[list] = None) -> bool:
        """
        Send accident report to Central Unit via HTTP POST (multipart/form-data).
        
        Implements the Reporter protocol's report() method.
        Uses context-manager-safe file handles to prevent resource leaks.
        """
        url = f"{self.server_url}{EVENT_ACCIDENT_REPORT}"
        files = []
        file_handles = []
        
        try:
            if media_paths:
                for path in media_paths[:5]:
                    if os.path.exists(path):
                        mime, _ = mimetypes.guess_type(path)
                        mime = mime or 'application/octet-stream'
                        fh = open(path, 'rb')
                        file_handles.append(fh)
                        files.append(('media', (os.path.basename(path), fh, mime)))
            
            response = requests.post(url, data=payload, files=files, timeout=15)
            
            if response.status_code in (200, 201):
                self.logger.info(f"Accident report posted successfully ({response.status_code})")
                return True
            
            self.logger.warning(f"Accident report POST failed: {response.status_code}")
            return False
                
        except Exception as e:
            self.logger.error(f"Error during report upload: {e}")
            return False
        finally:
            # Always close file handles
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    # Legacy alias for backward compatibility
    def report_accident(self, payload: Dict[str, Any], media_paths: Optional[list] = None) -> bool:
        """Alias for report() — kept for backward compatibility."""
        return self.report(payload, media_paths)

    def emit_heartbeat(self, node_id: str) -> None:
        """Send a heartbeat event to the server."""
        if self.connected:
            try:
                self.sio.emit(EVENT_HEARTBEAT, {'nodeId': str(node_id), 'status': 'active'})
            except Exception as e:
                self.logger.error(f"Heartbeat emit failed: {e}")
                raise
