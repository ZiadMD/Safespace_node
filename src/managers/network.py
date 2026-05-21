"""
Network Manager — Orchestrates all communication with the Central Unit.

Responsibilities:
    - HTTP heartbeats (POST /api/nodes/heartbeat every N seconds)
    - HTTP registration placeholder (POST /api/nodes/register — reserved)
    - Accident reporting via Socket.IO (node_accident_detected + ACK)
    - Receiving commands via raw WebSocket and dispatching to OutputManager
    - Accident-report cooldown / deduplication

Architecture:
    NetworkManager
        └── SocketHandler   (handlers/socket.py)
              ├── Socket.IO   → emit accident, receive ACK
              └── Raw WS      → receive commands from Central Unit
"""
import base64
import time
import shutil
import threading
from typing import Optional, Callable, Dict, Any, List
from datetime import datetime, timezone

import cv2
import psutil
import requests
import numpy as np
import supervision as sv

from utils.config import Config
from utils.logger import Logger
from utils.constants import (
    API_NODE_REGISTER,
    API_NODE_HEARTBEAT,
    COMMAND_ACCIDENT_DECISION,
    STATUS_CONFIRMED,
    STATUS_REJECTED,
    BACKEND_LANE_STATUS_MAP,
)
from handlers.socket import SocketHandler


# Type aliases
RoadUpdateCallback = Callable[[Dict[str, Any]], None]
ClearAccidentCallback = Callable[[], None]


class NetworkManager:
    """
    High-level orchestrator for Central Unit communication.

    Usage (from main.py):
        network = NetworkManager(
            config,
            on_road_update=output.apply_road_update,
            on_accident_cleared=output.clear_accident,
        )
        network.start()
        network.report_accident(detections, frame)
        network.stop()
    """

    def __init__(
        self,
        config: Config,
        on_road_update: Optional[RoadUpdateCallback] = None,
        on_accident_cleared: Optional[ClearAccidentCallback] = None,
    ):
        self.logger = Logger("NetworkManager")
        self.config = config

        # Callbacks to OutputManager
        self._on_road_update = on_road_update
        self._on_accident_cleared = on_accident_cleared

        # ── Config values ─────────────────────────────────────────
        self._server_url: str = config.get("network.server_url", "")
        self._node_id: str = config.get("node.id", "safe-space-node-001")
        self._heartbeat_interval: int = config.get_int("network.heartbeat_interval", 30)
        self._timeout: int = config.get_int("network.timeout", 10)
        self._accident_cooldown: int = config.get_int("network.accident_cooldown", 30)

        # Node info (for payloads)
        self._gps = None  # injected after init via set_gps_handler()
        self._lat = config.get("node.location.lat", "0")
        self._long = config.get("node.location.long", "0")
        self._num_lanes: int = config.get_int("node.lanes", 4)
        self._cam_width: int = config.get_int("camera.resolution.width", 1920)
        self._cam_height: int = config.get_int("camera.resolution.height", 1080)

        # ── Socket handler ────────────────────────────────────────
        self._socket = SocketHandler(config, on_command=self._on_command)

        # ── Heartbeat thread ──────────────────────────────────────
        self._hb_thread: Optional[threading.Thread] = None
        self._running = False
        self._start_time: float = time.time()  # for uptimeSec

        # ── Version info ──────────────────────────────────────────
        self._firmware_version = "1.0.0"
        self._model_version = "v1.0.0"

        # ── FPS tracking (updated externally by InputManager) ─────
        self._current_fps: float = 0.0
        self._target_fps: int = config.get_int("camera.fps", 30)

        # ── Cooldown tracking ─────────────────────────────────────
        self._last_report_time: float = 0.0

        # ── Incident tracking ─────────────────────────────────────
        self._active_incident_id: Optional[str] = None

    # ══════════════════════════════════════════════════════════════
    # Lifecycle
    # ══════════════════════════════════════════════════════════════

    def start(self):
        """Connect sockets and start the heartbeat loop."""
        self.logger.info("Starting Network Manager...")

        # Open Socket.IO + raw WebSocket channels
        self._socket.connect()

        # Start heartbeat thread
        self._running = True
        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="Heartbeat",
            daemon=True,
        )
        self._hb_thread.start()

        self.logger.info("Network Manager started")

    def stop(self):
        """Disconnect and stop background threads."""
        self._running = False
        self._socket.disconnect()

        if self._hb_thread:
            self._hb_thread.join(timeout=3.0)
            self._hb_thread = None

        self.logger.info("Network Manager stopped")

    # ══════════════════════════════════════════════════════════════
    # Heartbeat
    # ══════════════════════════════════════════════════════════════

    def _heartbeat_loop(self):
        """POST /api/nodes/heartbeat every N seconds."""
        while self._running:
            try:
                url = f"{self._server_url.rstrip('/')}{API_NODE_HEARTBEAT}"
                payload = {
                    "type": "heartbeat",
                    "nodeId": self._node_id,
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
                    "status": "online",
                    "uptimeSec": int(time.time() - self._start_time),
                    "health": self._get_health_metrics(),
                    "location": self._gps.get_location() if self._gps else {"lat": float(self._lat), "long": float(self._long), "fix": False},
                    "firmwareVersion": self._firmware_version,
                    "modelVersion": self._model_version,
                }
                resp = requests.post(url, json=payload, timeout=self._timeout)
                if resp.ok:
                    self.logger.debug(f"Heartbeat OK ({resp.status_code})")
                else:
                    self.logger.warning(f"Heartbeat failed: {resp.status_code} {resp.text[:100]}")
            except requests.RequestException as e:
                self.logger.warning(f"Heartbeat error: {e}")

            # Sleep in small increments so we can stop promptly
            for _ in range(self._heartbeat_interval * 10):
                if not self._running:
                    return
                time.sleep(0.1)

    def _get_health_metrics(self) -> Dict[str, float]:
        """
        Gather system health metrics using psutil.

        Returns dict matching backend schema:
            cpu, temperature, memory, network, storage, currentFps
        """
        # CPU usage (percent, non-blocking since interval=None uses cached)
        cpu = psutil.cpu_percent(interval=None)

        # Temperature — try to read from thermal sensors
        temperature = 0.0
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                # Pick the first available sensor group
                for entries in temps.values():
                    if entries:
                        temperature = entries[0].current
                        break
        except (AttributeError, Exception):
            pass  # Not available on all platforms

        # Memory usage (percent)
        memory = psutil.virtual_memory().percent

        # Network — approximate score: 100 if sockets connected, 0 otherwise
        network_score = 0.0
        if self._socket.is_sio_connected and self._socket.is_ws_connected:
            network_score = 100.0
        elif self._socket.is_sio_connected or self._socket.is_ws_connected:
            network_score = 50.0

        # Storage (root partition usage percent)
        try:
            disk = shutil.disk_usage("/")
            storage = (disk.used / disk.total) * 100.0
        except Exception:
            storage = 0.0

        return {
            "cpu": round(cpu, 1),
            "temperature": round(temperature, 1),
            "memory": round(memory, 1),
            "network": round(network_score, 1),
            "storage": round(storage, 1),
            "currentFps": round(self._current_fps, 1),
        }

    def update_fps(self, fps: float):
        """Called externally to update the current FPS for heartbeat reporting."""
        self._current_fps = fps

    def set_gps_handler(self, gps_handler):
        """Inject GPS handler so accident reports use live coordinates."""
        self._gps = gps_handler
        self.logger.info("GPS handler attached to NetworkManager")

    # ══════════════════════════════════════════════════════════════
    # Registration (reserved — not implemented on server yet)
    # ══════════════════════════════════════════════════════════════

    def register_node(self):
        """
        POST /api/nodes/register — reserved for future use.

        Called automatically when the server implements registration.
        Currently a no-op placeholder.
        """
        self.logger.info("Node registration is reserved — skipping")
        # Future implementation:
        # url = f"{self._server_url.rstrip('/')}{API_NODE_REGISTER}"
        # payload = { "nodeId": self._node_id, ... }
        # resp = requests.post(url, json=payload, timeout=self._timeout)

    # ══════════════════════════════════════════════════════════════
    # Accident Reporting
    # ══════════════════════════════════════════════════════════════

    def report_accident(self, detections: sv.Detections, frame: np.ndarray):
        """
        Build and send an accident report to the Central Unit via Socket.IO.

        Applies a cooldown to prevent spamming.

        Args:
            detections: supervision.Detections from the AI model.
            frame: The BGR frame where the accident was detected.
        """
        # Cooldown check
        now = time.time()
        if now - self._last_report_time < self._accident_cooldown:
            remaining = self._accident_cooldown - (now - self._last_report_time)
            self.logger.debug(f"Accident report cooldown — {remaining:.0f}s remaining")
            return

        self._last_report_time = now

        # Build payload in a background thread to avoid blocking AI
        threading.Thread(
            target=self._send_accident_report,
            args=(detections, frame),
            name="AccidentReport",
            daemon=True,
        ).start()

    def _send_accident_report(self, detections: sv.Detections, frame: np.ndarray):
        """Build the full payload and emit via Socket.IO (runs in bg thread)."""
        try:
            payload = self._build_accident_payload(detections, frame)
            response = self._socket.emit_accident(payload)

            if response and response.get("success"):
                self._active_incident_id = response.get("incidentId")
                self.logger.info(
                    f"Accident reported — incidentId={self._active_incident_id}, "
                    f"status={response.get('status')}"
                )
            else:
                msg = response.get("message", "Unknown") if response else "No response"
                self.logger.error(f"Accident report failed: {msg}")

        except Exception as e:
            self.logger.error(f"Accident report error: {e}")

    def _build_accident_payload(
        self, detections: sv.Detections, frame: np.ndarray
    ) -> Dict[str, Any]:
        """
        Convert supervision.Detections + frame into the backend payload.

        Payload shape:
            {
                "lat": float, "long": float,
                "lanNumber": int,
                "nodeId": str,
                "accidentPolygon": { "points": [...], "baseWidth": int, "baseHeight": int },
                "media": ["data:image/jpeg;base64,..."]
            }

        When multiple detections exist, accidentPolygon.points is a list of
        polygon arrays (one per detection).
        """
        # ── Polygon(s) from bounding boxes ────────────────────────
        polygons: List[List[Dict[str, int]]] = []
        for bbox in detections.xyxy:
            x1, y1, x2, y2 = bbox
            polygons.append([
                {"x": int(x1), "y": int(y1)},
                {"x": int(x2), "y": int(y1)},
                {"x": int(x2), "y": int(y2)},
                {"x": int(x1), "y": int(y2)},
            ])
            

        # Single detection → flat list; multiple → list of lists
        points = polygons[0] if len(polygons) == 1 else polygons

        # ── Detailed Detections ───────────────────────────────────
        detailed_detections = []
        for i in range(len(detections)):
            bbox = detections.xyxy[i]
            conf = detections.confidence[i] if detections.confidence is not None else 1.0
            cls_id = detections.class_id[i] if detections.class_id is not None else -1
            print(f'bbox: {bbox}')
            detailed_detections.append({
                "bbox": [int(x) for x in bbox],
                "confidence": float(conf),
                "classId": int(cls_id)
            })

        # ── Encode frame as base64 JPEG ───────────────────────────
        media: List[str] = []
        try:
            _, jpg_buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            b64 = base64.b64encode(jpg_buf.tobytes()).decode("ascii")
            media.append(f"data:image/jpeg;base64,{b64}")
        except Exception as e:
            self.logger.warning(f"Failed to encode frame: {e}")

        # Use live GPS if available, fall back to static config
        if self._gps:
            _loc = self._gps.get_location()
            _lat = _loc["lat"]
            _lon = _loc["long"]
            if not _loc["fix"]:
                self.logger.debug("GPS no fix � using config fallback coordinates")
        else:
            _lat = float(self._lat)
            _lon = float(self._long)

        return {
            "lat": _lat,
            "long": _lon,
            "lanNumber": self._num_lanes,
            "nodeId": self._node_id,
            "accidentPolygon": {
                "points": points,
                "baseWidth": self._cam_width,
                "baseHeight": self._cam_height,
            },
            "detections": detailed_detections,
            "media": media,
        }

    # ══════════════════════════════════════════════════════════════
    # Command Dispatch (from raw WebSocket)
    # ══════════════════════════════════════════════════════════════

    def _on_command(self, message: Dict[str, Any]):
        """
        Dispatch an incoming command from the Central Unit.

        Expected message shape:
            {
                "type": "command",
                "commandId": "accident-decision",
                "data": { "incidentId": ..., "status": "CONFIRMED"|"REJECTED", ... }
            }
        """
        msg_type = message.get("type")
        command_id = message.get("commandId")

        if msg_type != "command":
            self.logger.debug(f"Ignoring non-command message: type={msg_type}")
            return

        if command_id == COMMAND_ACCIDENT_DECISION:
            self._handle_accident_decision(message.get("data", {}))
        else:
            self.logger.warning(f"Unknown commandId: {command_id}")

    def _handle_accident_decision(self, data: Dict[str, Any]):
        """
        Handle an accident-decision command from the Central Unit admin.

        CONFIRMED → apply speed limit + lane states to the display.
        REJECTED  → clear the accident alert, restore defaults.
        """
        status = data.get("status")
        incident_id = data.get("incidentId", "?")

        if status == STATUS_CONFIRMED:
            self.logger.info(f"Accident CONFIRMED (incident={incident_id})")

            # Translate backend payload → OutputManager format
            speed_limit = data.get("speedLimit")
            lane_states_raw = data.get("laneStates", [])

            # Map backend lane names ("open") → display names ("up")
            lane_states = [
                BACKEND_LANE_STATUS_MAP.get(s, s) for s in lane_states_raw
            ]

            road_update = {
                "lanes": lane_states,
                "speed_limit": speed_limit,
                "accident": True,
            }

            if self._on_road_update:
                self._on_road_update(road_update)

        elif status == STATUS_REJECTED:
            self.logger.info(f"Accident REJECTED (incident={incident_id})")
            self._active_incident_id = None

            if self._on_accident_cleared:
                self._on_accident_cleared()

        else:
            self.logger.warning(f"Unknown accident-decision status: {status}")

    # ── Properties ────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        """True if at least one channel is connected."""
        return self._socket.is_sio_connected or self._socket.is_ws_connected

    @property
    def active_incident_id(self) -> Optional[str]:
        return self._active_incident_id
