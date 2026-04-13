"""
Command Handler — dispatches WebSocket commands from the Central Unit.

Handles road updates, accident decisions, and stream control commands.
"""
import json
import time
import threading
from typing import Optional, Callable

import websocket

from core.config import Config
from core.logger import Logger
from core.message_bus import MessageBus
from core.constants import (
    TOPIC_ROAD_UPDATE, TOPIC_ACCIDENT_DECISION, TOPIC_MODE_CHANGED,
    COMMAND_ACCIDENT_DECISION, COMMAND_START_STREAM, COMMAND_STOP_STREAM,
)


class CommandHandler:
    """Listens for WebSocket commands and publishes events to the bus."""

    def __init__(self, config: Config, bus: MessageBus):
        self.logger = Logger("CommandHandler")
        self.config = config
        self.bus = bus

        self._server_url = config.get('network.server_url', '')
        self._node_id = config.get('node.id', 'unknown')
        self._ws_path = config.get('network.ws_path', '/ws/commands')

        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._running = False
        self._connected = False
        self._reconnect_delay = 1

    def start(self):
        """Start the WebSocket listener in a background thread."""
        self._running = True
        self._connect()

    def stop(self):
        """Stop the WebSocket listener."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass

    def _build_ws_url(self) -> str:
        base = self._server_url
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://"):]
        else:
            ws_base = "ws://" + base
        return f"{ws_base.rstrip('/')}{self._ws_path}?client=node"

    def _connect(self):
        """Start / restart the WebSocket connection."""
        if not self._server_url:
            self.logger.info("No server URL — WebSocket disabled")
            return

        url = self._build_ws_url()
        self.logger.info(f"WebSocket connecting to {url}")

        self._ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            name="WSCommandListener",
            daemon=True,
        )
        self._ws_thread.start()

    def _on_open(self, ws):
        self._connected = True
        self._reconnect_delay = 1
        register_msg = {
            "type": "register",
            "nodeId": self._node_id,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }
        try:
            ws.send(json.dumps(register_msg))
            self.logger.info("WebSocket connected — registered")
        except Exception as e:
            self.logger.error(f"WebSocket register failed: {e}")

    def _on_message(self, ws, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            self.logger.warning(f"Non-JSON WebSocket message: {message[:120]}")
            return

        msg_type = data.get("type", "unknown")
        self.logger.info(f"WebSocket command: {msg_type}")
        self._dispatch(data)

    def _dispatch(self, data: dict):
        """Route the command to the appropriate bus topic."""
        msg_type = data.get("type", "")

        if msg_type == "road-update":
            self.bus.publish(TOPIC_ROAD_UPDATE, data)

        elif msg_type == COMMAND_ACCIDENT_DECISION:
            self.bus.publish(TOPIC_ACCIDENT_DECISION, data)

        elif msg_type == COMMAND_START_STREAM:
            self.logger.info("Server requested streaming mode")
            self.bus.publish(TOPIC_MODE_CHANGED, {"mode": "streaming", "source": "server"})

        elif msg_type == COMMAND_STOP_STREAM:
            self.logger.info("Server requested normal mode")
            self.bus.publish(TOPIC_MODE_CHANGED, {"mode": "normal", "source": "server"})

        else:
            self.logger.debug(f"Unhandled command type: {msg_type}")

    def _on_error(self, ws, error):
        self.logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self._connected = False
        self.logger.warning(f"WebSocket closed (code={close_status_code})")
        if self._running:
            delay = min(self._reconnect_delay, 30)
            self.logger.info(f"WebSocket reconnecting in {delay}s")
            time.sleep(delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 30)
            self._connect()

    @property
    def is_connected(self) -> bool:
        return self._connected
