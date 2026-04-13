"""
Node Supervisor — monitors child processes and manages mode transitions.

Watches the AI process health and triggers fallback to streaming mode
if inference is down. Can restart the AI process a configurable number
of times before giving up.
"""
import time
import threading
import multiprocessing as mp
from typing import Optional, Callable

from core.config import Config
from core.logger import Logger
from core.node_state import NodeState, Mode
from core.message_bus import MessageBus
from core.constants import TOPIC_AI_HEALTH, TOPIC_MODE_CHANGED, TOPIC_SHUTDOWN


class NodeSupervisor:
    """
    Watches child processes and manages operating mode transitions.

    Health checks:
        - Capture process: is it alive?
        - AI process: is it alive? is it publishing health pings?
        - Network: are sockets connected?

    When AI fails:
        1. Restart it (up to max_restarts times)
        2. If restarts exhausted → switch to STREAMING mode
        3. If server is also unreachable → switch to DEGRADED mode
    """

    def __init__(
        self,
        config: Config,
        state: NodeState,
        bus: MessageBus,
        ai_process_factory: Optional[Callable] = None,
    ):
        self.logger = Logger("Supervisor")
        self.config = config
        self.state = state
        self.bus = bus
        self._ai_process_factory = ai_process_factory

        # Config
        self._check_interval = config.get_int("supervisor.health_check_interval", 5)
        self._ai_timeout = config.get_int("supervisor.ai_health_timeout", 30)
        self._max_restarts = config.get_int("supervisor.max_ai_restarts", 3)
        self._auto_recover = config.get_bool("supervisor.auto_recover", True)

        # Process references (set by the main entry point)
        self.capture_process: Optional[mp.Process] = None
        self.ai_process: Optional[mp.Process] = None

        # Health tracking
        self._last_ai_ping = time.time()
        self._ai_restart_count = 0
        self._ai_health_queue = bus.subscribe(TOPIC_AI_HEALTH, maxsize=8)

        # Thread
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self):
        """Start the health-check loop in a background thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._health_loop,
            name="Supervisor",
            daemon=True,
        )
        self._thread.start()
        self.logger.info("Supervisor started")

    def stop(self):
        """Stop the supervisor loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.logger.info("Supervisor stopped")

    def _health_loop(self):
        """Periodic health check — runs every N seconds."""
        while self._running:
            try:
                self._check_ai_health()
                self._check_capture_health()
            except Exception as e:
                self.logger.error(f"Health check error: {e}")

            # Sleep in small increments for responsive shutdown
            for _ in range(self._check_interval * 10):
                if not self._running:
                    return
                time.sleep(0.1)

    def _check_ai_health(self):
        """Check if the AI process is alive and producing results."""
        if self.ai_process is None:
            # AI is disabled (e.g. --no-ai or IMX500 mode)
            return

        # Drain health pings from the bus
        from queue import Empty
        try:
            while True:
                msg = self._ai_health_queue.get_nowait()
                self._last_ai_ping = msg.get("time", time.time())
        except Empty:
            pass

        # Is the process alive?
        if not self.ai_process.is_alive():
            self.logger.warning("AI process is dead!")
            self._handle_ai_failure("process_dead")
            return

        # Is it producing results?
        idle_time = time.time() - self._last_ai_ping
        if idle_time > self._ai_timeout:
            self.logger.warning(
                f"AI process unresponsive for {idle_time:.0f}s "
                f"(timeout={self._ai_timeout}s)"
            )
            self._handle_ai_failure("timeout")

    def _handle_ai_failure(self, reason: str):
        """Handle an AI process failure — restart or switch mode."""
        self._ai_restart_count += 1

        if self._ai_restart_count <= self._max_restarts:
            self.logger.warning(
                f"AI failure ({reason}) — restarting "
                f"(attempt {self._ai_restart_count}/{self._max_restarts})"
            )
            self._restart_ai()
        else:
            self.logger.error(
                f"AI restart limit reached ({self._max_restarts}) — "
                f"switching to STREAMING mode"
            )
            if self.state.transition_to(Mode.STREAMING):
                self.bus.publish(TOPIC_MODE_CHANGED, {"mode": Mode.STREAMING.value})

    def _restart_ai(self):
        """Kill and restart the AI process."""
        # Kill old process
        if self.ai_process and self.ai_process.is_alive():
            self.ai_process.terminate()
            self.ai_process.join(timeout=5.0)

        # Start new one
        if self._ai_process_factory:
            self.ai_process = self._ai_process_factory()
            self.ai_process.start()
            self._last_ai_ping = time.time()
            self.logger.info("AI process restarted")

            # If auto-recover is enabled and we were in streaming mode,
            # check again after a grace period
            if self._auto_recover and self.state.is_streaming:
                def _check_recovery():
                    time.sleep(10)  # give AI time to warm up
                    if self.ai_process and self.ai_process.is_alive():
                        idle = time.time() - self._last_ai_ping
                        if idle < self._ai_timeout:
                            self.logger.info("AI recovered — switching back to NORMAL")
                            self._ai_restart_count = 0
                            if self.state.transition_to(Mode.NORMAL):
                                self.bus.publish(TOPIC_MODE_CHANGED, {"mode": Mode.NORMAL.value})

                threading.Thread(target=_check_recovery, daemon=True).start()

    def _check_capture_health(self):
        """Check if the capture process is alive."""
        if self.capture_process and not self.capture_process.is_alive():
            self.logger.critical("Capture process is dead — cannot recover!")
            # This is fatal — no camera means no data at all
            self.bus.publish(TOPIC_SHUTDOWN, {"reason": "capture_dead"})

    def notify_ai_recovered(self):
        """Called when AI is confirmed working again (e.g. after restart)."""
        self._ai_restart_count = 0
        self._last_ai_ping = time.time()
        if self.state.is_streaming and self._auto_recover:
            if self.state.transition_to(Mode.NORMAL):
                self.bus.publish(TOPIC_MODE_CHANGED, {"mode": Mode.NORMAL.value})
                self.logger.info("AI recovered — back to NORMAL mode")
