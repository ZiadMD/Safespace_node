"""
GPS Handler - Reads location data from SIM808 module over UART.

Responsibilities:
    - Powers on the GPS subsystem via AT commands
    - Polls for location at a configurable interval
    - Parses NMEA-style response from AT+CGNSINF
    - Exposes get_location() for other managers to call
    - Tracks GPS fix status and failure count
"""
import time
import threading
import serial
from typing import Optional, Dict, Any

from utils.logger import Logger
from utils.failures import GPSError, FailureManager

class GPSHandler:

    """
    Manages communication with the SIM808 GPS module over UART.

    Usage (from main.py):
        gps = GPSHandler(config)
        gps.start()
        location = gps.get_location()
        gps.stop()
    """
    def __init__(self, config):
        self.logger = Logger("GPSHandler")
        self.config = config

        self._port: str = config.get("gps.port", "/dev/ttyAMA0")
        self._baud: int = config.get_int("gps.baud_rate", 9600)
        self._poll_interval: int = config.get_int("gps.poll_interval", 10)
        self._timeout: int = config.get_int("gps.timeout", 2)
        self._enabled: bool = config.get("gps.enabled", True)

        self._serial: Optional[serial.Serial] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        self._lat: Optional[float] = None
        self._long: Optional[float] = None
        self._has_fix: bool = False
        self._consecutive_failures: int = 0
        self._max_failures: int = 10
        self._failure_manager = FailureManager()

        # Last location persisted to config (avoids redundant file writes)
        self._last_saved_lat: Optional[float] = None
        self._last_saved_long: Optional[float] = None

    def start(self):
        if not self._enabled:
            self.logger.info("GPS is disabled in config - skipping")
            return

        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._baud,
                timeout=self._timeout,
            )
            self.logger.info(f"Serial port opened: {self._port} @ {self._baud} baud")
        except serial.SerialException as e:
            self.logger.error(f"Failed to open serial port {self._port}: {e}")
            return

        # Sync with the module and silence command echo before issuing commands.
        # The SIM808 boots with echo ON and persists the setting, so otherwise
        # every reply starts with the echoed command - the source of the
        # intermittent power-on parse failures.
        self._sync_modem()

        if not self._power_on_gps():
            # Non-fatal: GNSS power state persists across sessions, so the module
            # may already be on. Start polling anyway; the poll loop has its own
            # failure tracking to catch a genuinely unresponsive module.
            self.logger.warning(
                "GPS power-on not acknowledged - starting poll loop anyway"
            )

        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="GPSPoller",
            daemon=True,
        )
        self._thread.start()
        self.logger.info("GPS Handler started")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._serial and self._serial.is_open:
            self._serial.close()
            self.logger.info("Serial port closed")
        self.logger.info("GPS Handler stopped")


    def _send_at(self, command: str, wait: float = 1.0) -> str:
        """
        Send an AT command and return the full modem reply.

        Drains the serial buffer until the reply contains a terminator
        ("OK"/"ERROR") or `wait` seconds elapse, instead of grabbing a single
        in_waiting snapshot. This prevents capturing only a partial reply (e.g.
        the echoed command without the trailing OK), which previously caused
        power-on to fail intermittently.
        """
        if not self._serial or not self._serial.is_open:
            return ""
        try:
            self._serial.reset_input_buffer()
            self._serial.write(f"{command}\r\n".encode())

            buffer = bytearray()
            deadline = time.time() + max(wait, 0.5)
            while time.time() < deadline:
                pending = self._serial.in_waiting
                if pending:
                    buffer += self._serial.read(pending)
                    if b"OK" in buffer or b"ERROR" in buffer:
                        break
                else:
                    time.sleep(0.02)
            return buffer.decode(errors="ignore")
        except serial.SerialException as e:
            self.logger.warning(f"Serial error sending '{command}': {e}")
            return ""

    def _sync_modem(self):
        """Wake the modem (AT) and disable command echo (ATE0)."""
        for _ in range(3):
            if "OK" in self._send_at("AT", wait=1.0):
                break
        self._send_at("ATE0", wait=1.0)

    def _power_on_gps(self) -> bool:
        self.logger.info("Powering on GPS subsystem...")
        for attempt in range(1, 4):
            response = self._send_at("AT+CGNSPWR=1", wait=2.0)
            if "OK" in response:
                self.logger.info("GPS subsystem powered on")
                return True
            self.logger.warning(
                f"GPS power-on attempt {attempt}/3 failed. Response: {response!r}"
            )
            time.sleep(1.0)
        self.logger.error("GPS power-on failed after 3 attempts")
        return False

    def _poll_loop(self):
        self.logger.info(f"GPS polling started (every {self._poll_interval}s)")
        while self._running:
            self._poll_once()
            for _ in range(self._poll_interval * 10):
                if not self._running:
                    return
                time.sleep(0.1)

    def _poll_once(self):
        response = self._send_at("AT+CGNSINF", wait=1.0)
        if not response:
            self._consecutive_failures += 1
            self.logger.warning(
                f"GPS poll got no response "
                f"(failure {self._consecutive_failures}/{self._max_failures})"
            )
            if self._consecutive_failures >= self._max_failures:
                self.logger.error("GPS module appears unresponsive - check wiring")
                self._failure_manager.record_failure(
                    GPSError("GPS module unresponsive - check wiring", critical=True)
                )
            return

        parsed = self._parse_cgnsinf(response)
        if parsed is None:
            return

        if parsed["fix"]:
            with self._lock:
                self._lat = parsed["lat"]
                self._long = parsed["long"]
                self._has_fix = True
                self._consecutive_failures = 0
            # Log the live location and persist it as the config fallback.
            self.logger.info(f"GPS fix: lat={parsed['lat']}, long={parsed['long']}")
            self._persist_location(parsed["lat"], parsed["long"])
        else:
            with self._lock:
                self._has_fix = False
            self.logger.debug("GPS: no fix yet (antenna needs open sky)")

    def _persist_location(self, lat: float, long: float):
        """
        Save the latest fix to the config (node.location) so that if GPS later
        loses its fix, get_location() falls back to the last known position.
        Only writes when the location actually changed, to limit file writes.
        """
        if lat == self._last_saved_lat and long == self._last_saved_long:
            return
        try:
            if self.config.update_location(lat, long):
                self._last_saved_lat = lat
                self._last_saved_long = long
        except Exception as e:
            self.logger.warning(f"Failed to save GPS location to config: {e}")

    def _parse_cgnsinf(self, response: str) -> Optional[Dict[str, Any]]:
        try:
            for line in response.splitlines():
                if "+CGNSINF:" not in line:
                    continue
                data = line.split(":")[1].strip()
                parts = data.split(",")

                if len(parts) < 5:
                    self.logger.warning(f"GPS response too short: {parts}")
                    return None

                fix_status = parts[1].strip()

                if fix_status != "1":
                    return {"fix": False, "lat": None, "long": None}

                lat_str = parts[3].strip()
                lon_str = parts[4].strip()

                if not lat_str or not lon_str:
                    return {"fix": False, "lat": None, "long": None}

                return {
                    "fix": True,
                    "lat": float(lat_str),
                    "long": float(lon_str),
                }

            self.logger.warning("No +CGNSINF line found in response")
            return None

        except (IndexError, ValueError) as e:
            self.logger.warning(f"GPS parse error: {e} | response: {response!r}")
            return None

    def get_location(self) -> Dict[str, Any]:
        """
        Returns latest GPS location.
        If no fix yet, falls back to static lat/long from config.
        """
        with self._lock:
            if self._has_fix and self._lat is not None:
                return {"lat": self._lat, "long": self._long, "fix": True}

        fallback_lat = float(self.config.get("node.location.lat", "0"))
        fallback_long = float(self.config.get("node.location.long", "0"))
        return {"lat": fallback_lat, "long": fallback_long, "fix": False}

    @property
    def has_fix(self) -> bool:
        with self._lock:
            return self._has_fix

    @property
    def is_enabled(self) -> bool:
        return self._enabled
