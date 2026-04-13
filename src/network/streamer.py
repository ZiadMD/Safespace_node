"""
Video Streamer — MJPEG over WebSocket to the Central Unit.

Active only in STREAMING mode. Reads frames from shared memory
and sends them as binary WebSocket messages.
"""
import time
import json
import asyncio
from queue import Empty
from typing import Optional

import cv2
import numpy as np

from core.config import Config
from core.logger import Logger
from core.shared_memory import SharedFrameSlots
from core.message_bus import MessageBus
from core.constants import TOPIC_MODE_CHANGED


class VideoStreamer:
    """
    Streams JPEG frames over WebSocket to the Central Unit.

    Protocol: binary WebSocket frames containing:
        [4 bytes: header length] [JSON header] [JPEG data]

    Only active when mode == "streaming".
    """

    def __init__(
        self,
        config: Config,
        bus: MessageBus,
        shared_slots: Optional[SharedFrameSlots],
    ):
        self.logger = Logger("VideoStreamer")
        self.config = config
        self.bus = bus
        self.shared_slots = shared_slots

        self._stream_fps = config.get_int("streaming.fps", 10)
        self._jpeg_quality = config.get_int("streaming.quality", 50)
        self._node_id = config.get("node.id", "unknown")
        self._frame_interval = 1.0 / self._stream_fps if self._stream_fps > 0 else 0.1
        self._active = False
        self._ws = None  # WebSocket reference

        self._mode_queue = bus.subscribe(TOPIC_MODE_CHANGED, maxsize=4)

    def set_websocket(self, ws):
        """Set the WebSocket reference for sending frames."""
        self._ws = ws

    async def run(self, stop_event: asyncio.Event):
        """Main loop — streams frames when in STREAMING mode."""
        self.logger.info(
            f"Streamer ready (fps={self._stream_fps}, quality={self._jpeg_quality})"
        )

        while not stop_event.is_set():
            # Check for mode changes
            try:
                while True:
                    msg = self._mode_queue.get_nowait()
                    new_active = msg.get("mode") == "streaming"
                    if new_active != self._active:
                        self._active = new_active
                        if self._active:
                            self.logger.info("Streaming STARTED")
                        else:
                            self.logger.info("Streaming STOPPED")
            except Empty:
                pass

            if self._active and self.shared_slots:
                await self._stream_frame()
                await asyncio.sleep(self._frame_interval)
            else:
                await asyncio.sleep(0.5)

        self.logger.info("Streamer stopped")

    async def _stream_frame(self):
        """Encode and send the latest frame."""
        if self.shared_slots is None:
            return

        result = self.shared_slots.read_latest()
        if result is None:
            return

        frame, ts, fid = result

        try:
            _, jpg = cv2.imencode(
                ".jpg", frame,
                [cv2.IMWRITE_JPEG_QUALITY, self._jpeg_quality]
            )

            header = json.dumps({
                "type": "stream_frame",
                "nodeId": self._node_id,
                "timestamp": ts,
                "frameId": int(fid),
            }).encode("utf-8")

            # Binary protocol: [4 bytes header_len][header][jpeg]
            payload = (
                len(header).to_bytes(4, "big")
                + header
                + jpg.tobytes()
            )

            if self._ws and hasattr(self._ws, 'send'):
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None, lambda: self._ws.send(payload, opcode=2)
                )
        except Exception as e:
            self.logger.debug(f"Stream frame failed: {e}")

    @property
    def is_active(self) -> bool:
        return self._active
