"""
Socket Handler - Low-level network communication with Central Unit.
"""
import socketio
import requests
import os
import mimetypes
from typing import Optional, Dict, Any, Callable
from utils.constants import (EVENT_ROAD_UPDATE, EVENT_CENTRAL_UNIT_UPDATE, 
                             EVENT_HEARTBEAT, EVENT_ACCIDENT_REPORT)


class SocketHandler:
    """Handles low-level network communication (WebSockets and HTTP POST)."""
    
    def __init__(self, server_url: str, on_central_unit_update: Optional[Callable] = None):
        """
        Initialize socket handler.
        
        Args:
            server_url: URL of the Central Unit server
            on_central_unit_update: Callback for updates from the Central Unit
        """
        self.server_url = server_url
        self.sio = socketio.Client()
        self.connected = False
        self.on_central_unit_update = on_central_unit_update
        
        self._setup_handlers()

    def _setup_handlers(self):
        """Setup socket.io event handlers."""
        @self.sio.on('connect')
        def on_connect():
            self.connected = True
            # Safely extract transport name
            transport = "unknown"
            try:
                transport = self.sio.eio.transport
            except Exception:
                pass
            print(f"[Network] Connected to Central Unit at {self.server_url} (Transport: {transport})")

        @self.sio.on('disconnect')
        def on_disconnect():
            self.connected = False
            print("[Network] Disconnected from Central Unit")

        # Catch-all for debugging incoming events from Central Unit
        @self.sio.on('*')
        def catch_all(event, data):
            print(f"[DEBUG] Socket Event Received: '{event}' | Data: {data}")
            # Route specific events to our handler
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
            print(f"[Network] Connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from the server."""
        if self.connected:
            self.sio.disconnect()

    def report_accident(self, payload: Dict[str, Any], media_paths: Optional[list] = None) -> bool:
        """
        Send accident report to Central Unit via HTTP POST (multipart/form-data).
        """
        url = f"{self.server_url}{EVENT_ACCIDENT_REPORT}"
        files = []
        
        try:
            if media_paths:
                for path in media_paths[:5]:
                    if os.path.exists(path):
                        mime, _ = mimetypes.guess_type(path)
                        mime = mime or 'application/octet-stream'
                        files.append(('media', (os.path.basename(path), open(path, 'rb'), mime)))
            
            response = requests.post(url, data=payload, files=files, timeout=15)
            
            # Close files
            for _, info in files:
                info[1].close()
                
            if response.status_code in (200, 201):
                print(f"[Network] Accident report successfully posted ({response.status_code})")
                return True
            
            print(f"[Network] POST failed: {response.status_code}")
            return False
                
        except Exception as e:
            print(f"[Network] Error during report upload: {e}")
            for _, info in files:
                info[1].close()
            return False

    def emit_heartbeat(self, node_id: str):
        """Send a heartbeat event to the server."""
        if self.connected:
            try:
                self.sio.emit(EVENT_HEARTBEAT, {'nodeId': str(node_id), 'status': 'active'})
            except Exception as e:
                raise e
