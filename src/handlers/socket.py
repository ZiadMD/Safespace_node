"""
Socket Handler — Low-level transport for Central Unit communication.

Two independent channels:
    1. Socket.IO  — emits accident reports, receives ACK
    2. Raw WebSocket — receives commands (accident-decision, etc.)

Both run in background threads and reconnect automatically.
"""
import json
import time
import threading
from typing import Optional, Callable, Dict, Any

import socketio
import websocket  # websocket-client

from utils.config import Config
from utils.logger import Logger


# Type alias for incoming command callback
CommandCallback = Callable[[Dict[str, Any]], None]


class SocketHandler:
    """
    Manages Socket.IO and raw WebSocket connections to the Central Unit.

    Usage:
        handler = SocketHandler(config, on_command=my_callback)
        handler.connect()      # opens both channels in bg threads
        handler.emit_accident(payload)  # send + ACK via Socket.IO
        handler.disconnect()   # clean shutdown
    """

    def __init__(self, config: Config, on_command: Optional[CommandCallback] = None):
        self.logger = Logger("SocketHandler")
        self.config = config
        self.on_command = on_command

        # ── Config ────────────────────────────────────────────────
        self._server_url: str = config.get("network.server_url", "")
        self._ws_path: str = config.get("network.ws_path", "/ws/nodes")
        self._node_id: str = config.get("node.id", "safe-space-node-001")
        self._timeout: int = config.get_int("network.timeout", 10)

        # ── Socket.IO client ─────────────────────────────────────
        self._sio = socketio.Client(
            reconnection=True,
            reconnection_delay=1,
            reconnection_delay_max=5,
            reconnection_attempts=0,  # unlimited
            logger=False,
            engineio_logger=False,
        )
        self._setup_sio_events()

        # ── Raw WebSocket ─────────────────────────────────────────
        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_running = False
        self._ws_reconnect_delay = 1  # exponential backoff start

        # ── State ─────────────────────────────────────────────────
        self._connected_sio = False
        self._connected_ws = False

    # ══════════════════════════════════════════════════════════════
    # Socket.IO
    # ══════════════════════════════════════════════════════════════

    def _setup_sio_events(self):
        """Register Socket.IO lifecycle events."""

        @self._sio.event
        def connect():
            self._connected_sio = True
            self.logger.info("Socket.IO connected to Central Unit")

        @self._sio.event
        def disconnect():
            self._connected_sio = False
            self.logger.warning("Socket.IO disconnected from Central Unit")

        @self._sio.event
        def connect_error(data):
            self.logger.error(f"Socket.IO connection error: {data}")

    def _connect_sio(self):
        """Connect the Socket.IO client (blocking, meant for bg thread)."""
        try:
            self.logger.info(f"Socket.IO connecting to {self._server_url} ...")
            self._sio.connect(self._server_url, wait_timeout=self._timeout)
        except Exception as e:
            self.logger.error(f"Socket.IO connect failed: {e}")

    def emit_accident(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Emit `node_accident_detected` via Socket.IO and wait for ACK.

        Args:
            payload: Full accident payload dict.

        Returns:
            The ACK response dict from the server, or None on failure.
        """
        if not self._connected_sio:
            self.logger.error("Cannot emit — Socket.IO not connected")
            return None

        from utils.constants import EVENT_ACCIDENT_DETECTED

        try:
            self.logger.info("Emitting accident report via Socket.IO...")
            response = self._sio.call(
                EVENT_ACCIDENT_DETECTED,
                payload,
                timeout=self._timeout,
            )
            self.logger.info(f"Accident ACK received: {response}")
            return response
        except Exception as e:
            self.logger.error(f"Socket.IO emit failed: {e}")
            return None

    # ══════════════════════════════════════════════════════════════
    # Raw WebSocket (commands from Central Unit)
    # ══════════════════════════════════════════════════════════════

    def _build_ws_url(self) -> str:
        """Build the raw WebSocket URL from config."""
        base = self._server_url
        # Convert http(s) to ws(s)
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://"):]
        else:
            ws_base = "ws://" + base

        return f"{ws_base.rstrip('/')}{self._ws_path}?client=node"

    def _on_ws_open(self, ws):
        """Called when raw WebSocket connects — send register message."""
        self._connected_ws = True
        self._ws_reconnect_delay = 1  # reset backoff

        # Registration (reserved — server doesn't require it yet)
        register_msg = {
            "type": "register",
            "nodeId": self._node_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }
        try:
            ws.send(json.dumps(register_msg))
            self.logger.info("WebSocket connected — register message sent")
        except Exception as e:
            self.logger.error(f"WebSocket register send failed: {e}")

    def _on_ws_message(self, ws, message: str):
        """Called when the Central Unit sends a command."""
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            self.logger.warning(f"WebSocket received non-JSON: {message[:120]}")
            return

        msg_type = data.get("type", "unknown")
        self.logger.info(f"WebSocket command received: type={msg_type}")

        if self.on_command:
            self.on_command(data)

    def _on_ws_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")

    def _on_ws_close(self, ws, close_status_code, close_msg):
        self._connected_ws = False
        self.logger.warning(f"WebSocket closed (code={close_status_code})")

        # Auto-reconnect with exponential backoff
        if self._ws_running:
            delay = min(self._ws_reconnect_delay, 30)
            self.logger.info(f"WebSocket reconnecting in {delay}s ...")
            time.sleep(delay)
            self._ws_reconnect_delay = min(self._ws_reconnect_delay * 2, 30)
            self._start_ws()

    def _start_ws(self):
        """Start / restart the raw WebSocket in a daemon thread."""
        url = self._build_ws_url()
        self.logger.info(f"WebSocket connecting to {url} ...")

        self._ws = websocket.WebSocketApp(
            url,
            on_open=self._on_ws_open,
            on_message=self._on_ws_message,
            on_error=self._on_ws_error,
            on_close=self._on_ws_close,
        )
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            name="WSCommandListener",
            daemon=True,
        )
        self._ws_thread.start()

    # ══════════════════════════════════════════════════════════════
    # Public lifecycle
    # ══════════════════════════════════════════════════════════════

    def connect(self):
        """Open both Socket.IO and raw WebSocket channels (non-blocking)."""
        # Socket.IO — connect in a background thread
        sio_thread = threading.Thread(
            target=self._connect_sio,
            name="SIOConnect",
            daemon=True,
        )
        sio_thread.start()

        # Raw WebSocket
        self._ws_running = True
        self._start_ws()

    def disconnect(self):
        """Cleanly close both channels."""
        self._ws_running = False

        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

        if self._sio.connected:
            try:
                self._sio.disconnect()
            except Exception:
                pass

        self.logger.info("Socket handler disconnected")

    # ── Properties ────────────────────────────────────────────────

    @property
    def is_sio_connected(self) -> bool:
        return self._connected_sio

    @property
    def is_ws_connected(self) -> bool:
        return self._connected_ws
