"""
Heartbeat — periodic health report coroutine.

Sends node status to the Central Unit every N seconds,
including mode, FPS, CPU, memory, and AI health.
"""
import time
import asyncio
import psutil
from typing import Optional

import requests

from core.config import Config
from core.logger import Logger
from core.node_state import NodeState
from core.constants import API_NODE_HEARTBEAT


class HeartbeatService:
    """Sends periodic heartbeats to the Central Unit."""

    def __init__(self, config: Config, state: NodeState):
        self.logger = Logger("Heartbeat")
        self.config = config
        self.state = state

        self._server_url = config.get('network.server_url', '')
        self._node_id = config.get('node.id', 'unknown')
        self._interval = config.get_int('network.heartbeat_interval', 5)
        self._num_lanes = config.get_int('node.lanes', 3)
        self._cam_width = config.get_int('camera.resolution.width', 640)
        self._cam_height = config.get_int('camera.resolution.height', 640)
        self._lat = config.get_float('node.latitude', 0.0)
        self._long = config.get_float('node.longitude', 0.0)

        self._current_fps = 0.0
        self._registered = False

    def update_fps(self, fps: float):
        self._current_fps = fps

    async def run(self, stop_event: asyncio.Event):
        """Heartbeat loop — runs until stop_event is set."""
        self.logger.info(f"Heartbeat started (interval={self._interval}s)")

        # Initial registration attempt
        await self._register()

        while not stop_event.is_set():
            try:
                await self._send_heartbeat()
            except Exception as e:
                self.logger.error(f"Heartbeat error: {e}")

            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._interval)
                break
            except asyncio.TimeoutError:
                pass

        self.logger.info("Heartbeat stopped")

    async def _register(self):
        """Register node with the Central Unit."""
        if not self._server_url:
            return
        url = f"{self._server_url.rstrip('/')}/api/nodes/register"
        payload = {
            "nodeId": self._node_id,
            "latitude": self._lat,
            "longitude": self._long,
            "cameraResolution": {
                "width": self._cam_width,
                "height": self._cam_height,
            },
            "numberOfLanes": self._num_lanes,
        }
        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, lambda: requests.post(url, json=payload, timeout=10)
            )
            if resp.ok:
                self._registered = True
                self.logger.info("Registered with Central Unit")
            else:
                self.logger.warning(f"Registration failed: {resp.status_code}")
        except Exception as e:
            self.logger.warning(f"Registration error: {e}")

    async def _send_heartbeat(self):
        """Send one heartbeat payload."""
        if not self._server_url:
            return

        url = f"{self._server_url.rstrip('/')}{API_NODE_HEARTBEAT}"
        payload = {
            "nodeId": self._node_id,
            "status": "online",
            "mode": self.state.mode.value,
            "currentFps": round(self._current_fps, 1),
            "systemHealth": self._get_health(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        }

        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, lambda: requests.post(url, json=payload, timeout=10)
            )
            if resp.ok:
                self.logger.debug("Heartbeat sent")
            else:
                self.logger.warning(f"Heartbeat response: {resp.status_code}")
        except requests.exceptions.ConnectionError:
            self.logger.warning("Heartbeat failed — server unreachable")
        except Exception as e:
            self.logger.error(f"Heartbeat error: {e}")

    @staticmethod
    def _get_health() -> dict:
        return {
            "cpuPercent": psutil.cpu_percent(interval=None),
            "memoryPercent": psutil.virtual_memory().percent,
        }
