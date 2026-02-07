"""
Network Worker — subscribes to AccidentDetected events from the bus
and handles all network communication with the Central Unit.

Replaces the old NetworkManager. Runs the heartbeat in a background thread
and reports accidents asynchronously. Publishes InstructionReceived events
when the server sends road-state updates.
"""
import threading
import time
from typing import Optional, Dict, Any

from core.bus import EventBus
from core.events import AccidentDetected, InstructionReceived, ConnectionStatus
from Handlers.Socket_Handler import SocketHandler
from utils.logger import Logger
from utils.config import Config
from utils.constants import DEFAULT_HEARTBEAT_INTERVAL
from utils.failures import FailureManager, NetworkError


class NetworkWorker:
    """
    Event-bus-driven network service.
    
    Subscribes to: AccidentDetected
    Publishes:     InstructionReceived, ConnectionStatus
    """

    def __init__(self, config: Config, bus: EventBus, stop_event: threading.Event):
        """
        Args:
            config: Application configuration.
            bus: Shared event bus.
            stop_event: Shared shutdown event.
        """
        self.config = config
        self.bus = bus
        self.stop_event = stop_event
        self.logger = Logger("NetworkWorker")
        self.failures = FailureManager(config.get('failures', {}))
        self.active = False

        # Low-level handler
        server_url = config.get('network.server_url')
        self.socket = SocketHandler(
            server_url,
            on_central_unit_update=self._on_server_update,
        )

        # Background threads
        self._heartbeat_thread: Optional[threading.Thread] = None

        # Subscribe to bus events
        self.bus.subscribe(AccidentDetected, self._on_accident_detected)

    def start(self) -> bool:
        """Establish connection and start heartbeat."""
        self.logger.info("Connecting to Safespace Central Unit...")

        try:
            if not self.socket.connect():
                raise NetworkError("Initial connection failed", critical=True)

            self.active = True
            self.bus.publish(ConnectionStatus(connected=True))
            self._start_heartbeat()
            return True
        except NetworkError as e:
            self.failures.record_failure(e)
            self.bus.publish(ConnectionStatus(connected=False, reason=str(e)))
            return False

    def stop(self) -> None:
        """Cleanly shutdown network operations."""
        self.active = False
        if self._heartbeat_thread:
            self._heartbeat_thread.join(timeout=2.0)
        self.socket.disconnect()
        self.logger.info("Network worker stopped")

    # ── Event Bus Handlers ──────────────────────────────────────────

    def _on_accident_detected(self, event: AccidentDetected) -> None:
        """Handle AccidentDetected events — send report to Central Unit."""
        node_id = self.config.get('node.id')
        location = self.config.get('node.location', {})

        payload = {
            'nodeId': str(node_id),
            'lat': str(location.get('lat', '0.0')),
            'long': str(location.get('long', '0.0')),
            'laneNumber': str(event.lane_number),
        }

        self.logger.info(
            f"Reporting accident for lane {event.lane_number} "
            f"(AI: {event.ai_detected}, model: {event.model_name})"
        )

        # Run the HTTP POST in a background thread to avoid blocking the bus
        def _report_task():
            try:
                success = self.socket.report(payload, event.media_paths)
                if not success:
                    self.failures.record_failure(
                        NetworkError("Failed to report accident")
                    )
            except Exception as e:
                self.failures.record_failure(
                    NetworkError(f"Accident reporting error: {e}")
                )

        threading.Thread(target=_report_task, daemon=True, name="AccidentReport").start()

    def _on_server_update(self, data: Dict[str, Any]) -> None:
        """Called by SocketHandler when the Central Unit sends an instruction."""
        self.logger.info(f"Server instruction received: {data}")
        self.bus.publish(InstructionReceived(data=data))

    # ── Heartbeat ───────────────────────────────────────────────────

    def _start_heartbeat(self) -> None:
        """Launch the background heartbeat thread."""
        def _loop():
            interval = self.config.get_int(
                'network.heartbeat_interval', DEFAULT_HEARTBEAT_INTERVAL
            )
            node_id = self.config.get('node.id')

            while self.active and not self.stop_event.is_set():
                try:
                    self.socket.emit_heartbeat(node_id)
                except Exception as e:
                    self.failures.record_failure(
                        NetworkError(f"Heartbeat failed: {e}")
                    )
                time.sleep(interval)

        self._heartbeat_thread = threading.Thread(
            target=_loop, daemon=True, name="Heartbeat"
        )
        self._heartbeat_thread.start()
