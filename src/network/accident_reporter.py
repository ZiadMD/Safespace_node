"""
Accident Reporter — sends accident reports to the Central Unit.

Watches the detection topic on the message bus and sends reports
with a cooldown to prevent spamming.
"""
import time
import base64
import asyncio
import multiprocessing as mp
from queue import Empty
from typing import Optional, Dict, Any, List

import cv2
import numpy as np
import requests

from core.config import Config
from core.logger import Logger
from core.shared_memory import SharedFrameSlots
from core.message_bus import MessageBus
from core.constants import TOPIC_DETECTION


class AccidentReporter:
    """Watches for detections and sends accident reports to the server."""

    def __init__(
        self,
        config: Config,
        bus: MessageBus,
        shared_slots: Optional[SharedFrameSlots],
    ):
        self.logger = Logger("AccidentReporter")
        self.config = config
        self.bus = bus
        self.shared_slots = shared_slots

        self._server_url = config.get('network.server_url', '')
        self._node_id = config.get('node.id', 'unknown')
        self._cooldown = config.get_int('network.accident_cooldown', 30)
        self._num_lanes = config.get_int('node.lanes', 3)
        self._lat = config.get_float('node.latitude', 0.0)
        self._long = config.get_float('node.longitude', 0.0)
        self._cam_width = config.get_int('camera.resolution.width', 640)
        self._cam_height = config.get_int('camera.resolution.height', 640)

        self._last_report_time = 0.0
        self._active_incident_id: Optional[str] = None
        self._detection_queue = bus.subscribe(TOPIC_DETECTION, maxsize=8)

        # Socket.IO (lazy import to avoid issues when network disabled)
        self._sio = None

    def set_sio(self, sio):
        """Set the Socket.IO client reference."""
        self._sio = sio

    async def run(self, stop_event: asyncio.Event):
        """Watch for detections and report accidents."""
        self.logger.info("Accident reporter started")

        while not stop_event.is_set():
            try:
                msg = self._detection_queue.get(timeout=1.0)
            except Empty:
                continue
            except Exception:
                await asyncio.sleep(0.5)
                continue

            # Cooldown check
            now = time.time()
            if now - self._last_report_time < self._cooldown:
                continue

            self._last_report_time = now
            await self._send_report(msg)

        self.logger.info("Accident reporter stopped")

    async def _send_report(self, detection_msg: dict):
        """Build and send the accident report."""
        try:
            # Get frame from shared memory
            frame = None
            if self.shared_slots:
                result = self.shared_slots.read_latest_copy()
                if result:
                    frame, _, _ = result

            payload = self._build_payload(detection_msg, frame)

            if self._sio and self._sio.connected:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    lambda: self._sio.call(
                        "node_accident_detected", payload, timeout=15
                    )
                )
                if response and response.get("success"):
                    self._active_incident_id = response.get("incidentId")
                    self.logger.info(
                        f"Accident reported — incidentId={self._active_incident_id}"
                    )
                else:
                    msg = response.get("message", "Unknown") if response else "No response"
                    self.logger.error(f"Accident report failed: {msg}")
            else:
                self.logger.warning("Cannot report accident — Socket.IO not connected")

        except Exception as e:
            self.logger.error(f"Accident report error: {e}")

    def _build_payload(self, detection_msg: dict, frame: Optional[np.ndarray]) -> dict:
        """Build the accident payload."""
        # Polygons from detection boxes
        polygons = []
        xyxy_list = detection_msg.get("xyxy", [])
        for bbox in xyxy_list:
            x1, y1, x2, y2 = bbox
            polygons.append([
                {"x": int(x1), "y": int(y1)},
                {"x": int(x2), "y": int(y1)},
                {"x": int(x2), "y": int(y2)},
                {"x": int(x1), "y": int(y2)},
            ])
        points = polygons[0] if len(polygons) == 1 else polygons

        # Encode frame as JPEG
        media = []
        if frame is not None:
            try:
                _, jpg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
                b64 = base64.b64encode(jpg.tobytes()).decode("ascii")
                media.append(f"data:image/jpeg;base64,{b64}")
            except Exception as e:
                self.logger.warning(f"Frame encode failed: {e}")

        return {
            "lat": float(self._lat),
            "long": float(self._long),
            "lanNumber": self._num_lanes,
            "nodeId": self._node_id,
            "accidentPolygon": {
                "points": points,
                "baseWidth": self._cam_width,
                "baseHeight": self._cam_height,
            },
            "media": media,
        }

    @property
    def active_incident_id(self) -> Optional[str]:
        return self._active_incident_id
