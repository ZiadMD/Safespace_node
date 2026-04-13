"""
Network Service — unified asyncio event loop for all network I/O.

Runs heartbeat, accident reporter, video streamer, and command handler
in a single thread with cooperative multitasking.
"""
import asyncio
import threading
from typing import Optional

import socketio

from core.config import Config
from core.logger import Logger
from core.node_state import NodeState
from core.shared_memory import SharedFrameSlots
from core.message_bus import MessageBus

from network.heartbeat import HeartbeatService
from network.accident_reporter import AccidentReporter
from network.command_handler import CommandHandler
from network.streamer import VideoStreamer


class NetworkService:
    """
    All network I/O in one asyncio event loop, one thread.

    Components:
        - HeartbeatService: periodic status to server
        - AccidentReporter: sends detection alerts
        - CommandHandler: receives WebSocket commands
        - VideoStreamer: MJPEG streaming in fallback mode
    """

    def __init__(
        self,
        config: Config,
        state: NodeState,
        bus: MessageBus,
        shared_slots: Optional[SharedFrameSlots],
    ):
        self.logger = Logger("NetworkService")
        self.config = config
        self.state = state
        self.bus = bus
        self.shared_slots = shared_slots

        self._server_url = config.get('network.server_url', '')
        self._node_id = config.get('node.id', 'unknown')

        # Socket.IO client
        self._sio = socketio.Client(
            reconnection=True,
            reconnection_attempts=0,  # infinite
            reconnection_delay=2,
            reconnection_delay_max=30,
            logger=False,
        )
        self._setup_sio_events()

        # Sub-services
        self.heartbeat = HeartbeatService(config, state)
        self.accident_reporter = AccidentReporter(config, bus, shared_slots)
        self.accident_reporter.set_sio(self._sio)
        self.command_handler = CommandHandler(config, bus)
        self.streamer = VideoStreamer(config, bus, shared_slots)

        # Thread + event loop
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event: Optional[asyncio.Event] = None

    def _setup_sio_events(self):
        """Register Socket.IO event handlers."""
        @self._sio.event
        def connect():
            self.logger.info("Socket.IO connected")

        @self._sio.event
        def disconnect():
            self.logger.warning("Socket.IO disconnected")

        @self._sio.event
        def connect_error(data):
            self.logger.error(f"Socket.IO connection error: {data}")

    def start(self):
        """Start all network services in a background thread."""
        self._thread = threading.Thread(
            target=self._run_event_loop,
            name="NetworkService",
            daemon=True,
        )
        self._thread.start()

        # Start WebSocket command listener (runs in its own thread internally)
        self.command_handler.start()

        # Connect Socket.IO
        self._connect_sio()

    def _connect_sio(self):
        """Connect Socket.IO in a background thread."""
        if not self._server_url:
            self.logger.info("No server URL — Socket.IO disabled")
            return

        def _connect():
            try:
                sio_url = self._server_url.rstrip('/')
                self._sio.connect(
                    sio_url,
                    transports=['websocket', 'polling'],
                    wait_timeout=10,
                )
            except Exception as e:
                self.logger.warning(f"Socket.IO connect failed: {e}")

        threading.Thread(target=_connect, daemon=True).start()

    def _run_event_loop(self):
        """Run the asyncio event loop with all coroutines."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()

        try:
            self._loop.run_until_complete(asyncio.gather(
                self.heartbeat.run(self._stop_event),
                self.accident_reporter.run(self._stop_event),
                self.streamer.run(self._stop_event),
            ))
        except Exception as e:
            self.logger.error(f"Network event loop error: {e}")
        finally:
            self._loop.close()

    def stop(self):
        """Stop all network services."""
        # Signal async tasks to stop
        if self._loop and self._stop_event:
            self._loop.call_soon_threadsafe(self._stop_event.set)

        # Stop command handler
        self.command_handler.stop()

        # Disconnect Socket.IO
        try:
            if self._sio.connected:
                self._sio.disconnect()
        except Exception:
            pass

        # Wait for thread
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None

        self.logger.info("Network service stopped")

    @property
    def is_connected(self) -> bool:
        return self._sio.connected
