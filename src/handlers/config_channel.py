"""
Config Channel Handler — dedicated WebSocket transport for CU-driven config
updates.

Deliberately separate from the command WebSocket (handlers/socket.py) so a
config push can never be confused with an accident-decision command. Reuses
the same reconnect/backoff shape as SocketHandler's raw WS channel:
exponential backoff from 1s, capped at 30s, reset on successful connect.

This class is transport only — it opens the socket, frames JSON in/out, and
reconnects. Message semantics (validate / persist / restart / rollback)
live in managers/config_manager.py, mirroring how SocketHandler stays dumb
and NetworkManager owns the command dispatch logic.
"""
import json
import threading
import time
from typing import Optional, Callable, Dict, Any

import websocket  # websocket-client

from utils.config import Config
from utils.logger import Logger


ConfigMessageCallback = Callable[[Dict[str, Any]], None]


class ConfigChannelHandler:
    """
    Manages the dedicated config-update WebSocket connection to the Central Unit.

    Usage:
        channel = ConfigChannelHandler(config, on_message=my_callback, on_connect=my_connect_cb)
        channel.connect()          # opens the channel in a bg thread
        channel.send({...})        # send a JSON message (ack / applied)
        channel.disconnect()       # clean shutdown
    """

    def __init__(
        self,
        config: Config,
        on_message: Optional[ConfigMessageCallback] = None,
        on_connect: Optional[Callable[[], None]] = None,
    ):
        self.logger = Logger("ConfigChannelHandler")
        self.config = config
        self.on_message = on_message
        self.on_connect = on_connect

        self._server_url: str = config.get("network.server_url", "")
        self._config_ws_path: str = config.get("network.config_ws_path", "/ws/nodes/config")
        self._node_id: str = config.get("node.id", "safe-space-node-001")

        self._ws: Optional[websocket.WebSocketApp] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._running = False
        self._reconnect_delay = 1  # exponential backoff start
        self._connected = False

    def _build_ws_url(self) -> str:
        """Build the config-channel WebSocket URL from config."""
        base = self._server_url
        if base.startswith("https://"):
            ws_base = "wss://" + base[len("https://"):]
        elif base.startswith("http://"):
            ws_base = "ws://" + base[len("http://"):]
        else:
            ws_base = "ws://" + base

        return f"{ws_base.rstrip('/')}{self._config_ws_path}?client=node&nodeId={self._node_id}"

    def _on_open(self, ws):
        self._connected = True
        self._reconnect_delay = 1  # reset backoff
        self.logger.info("Config channel connected")
        if self.on_connect:
            try:
                self.on_connect()
            except Exception as e:
                self.logger.error(f"Config channel on_connect callback failed: {e}")

    def _on_message(self, ws, message: str):
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            self.logger.warning(f"Config channel received non-JSON: {message[:120]}")
            return

        self.logger.info(f"Config channel message received: type={data.get('type')}")
        if self.on_message:
            self.on_message(data)

    def _on_error(self, ws, error):
        self.logger.error(f"Config channel error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        self._connected = False
        self.logger.warning(f"Config channel closed (code={close_status_code})")

        if self._running:
            delay = min(self._reconnect_delay, 30)
            self.logger.info(f"Config channel reconnecting in {delay}s ...")
            time.sleep(delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, 30)
            self._start()

    def _start(self):
        """Start / restart the config WebSocket in a daemon thread."""
        url = self._build_ws_url()
        self.logger.info(f"Config channel connecting to {url} ...")

        self._ws = websocket.WebSocketApp(
            url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            name="ConfigChannelListener",
            daemon=True,
        )
        self._ws_thread.start()

    # ══════════════════════════════════════════════════════════════
    # Public lifecycle
    # ══════════════════════════════════════════════════════════════

    def connect(self):
        """Open the config channel (non-blocking)."""
        self._running = True
        self._start()

    def disconnect(self):
        """Cleanly close the channel."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        self.logger.info("Config channel disconnected")

    def send(self, message: Dict[str, Any]) -> bool:
        """Send a JSON message (config.ack / config.applied). Returns True if sent."""
        if not self._connected or not self._ws:
            self.logger.warning(f"Cannot send — config channel not connected: {message.get('type')}")
            return False
        try:
            self._ws.send(json.dumps(message))
            return True
        except Exception as e:
            self.logger.error(f"Config channel send failed: {e}")
            return False

    @property
    def is_connected(self) -> bool:
        return self._connected
