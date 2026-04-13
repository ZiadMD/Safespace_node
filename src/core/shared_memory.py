"""
Shared Memory Frame Slots — Zero-copy frame sharing between processes.

Pre-allocates a fixed number of frame slots in shared memory.
Uses a shared memory control block for coordination instead of
mp.Value/mp.Lock which can hang on some platforms.
"""
import time
import struct
import numpy as np
from multiprocessing import shared_memory
from typing import Optional, Tuple

from core.logger import Logger

# Control block layout (stored at the start of shared memory):
#   [0:4]   latest_index   (int32)
#   [4:12]  frame_counter  (uint64)
#   [12:20] annotated_index (int32) + padding
#   [20:20+8*N] timestamps (float64 per slot)
# Then frame data follows after the control block.
CTRL_HEADER_SIZE = 64  # bytes reserved for control data


class SharedFrameSlots:
    """
    Fixed pre-allocated frame slots in shared memory.

    All processes access the same physical memory — no copies needed.
    Coordination via atomic-ish writes to a control block in shared memory
    (safe for single-writer scenarios like capture→AI).
    """

    def __init__(self, width: int = 640, height: int = 640, channels: int = 3,
                 num_slots: int = 3, shm_name: str = None):
        self.logger = Logger("SharedFrameSlots")
        self.width = width
        self.height = height
        self.channels = channels
        self.num_slots = num_slots
        self.frame_size = width * height * channels

        # Total: control block + N frame slots
        ts_block = 8 * num_slots  # float64 per slot
        total_ctrl = CTRL_HEADER_SIZE + ts_block
        total_bytes = total_ctrl + (num_slots * self.frame_size)

        if shm_name:
            # Attach to existing shared memory (child process)
            self._shm = shared_memory.SharedMemory(name=shm_name, create=False)
            self._owns_shm = False
        else:
            # Create new shared memory (parent process)
            self._shm = shared_memory.SharedMemory(create=True, size=total_bytes)
            # Initialize control block to zeros
            self._shm.buf[:total_ctrl] = b'\x00' * total_ctrl
            # Set latest_index to -1 (no frame yet)
            struct.pack_into('i', self._shm.buf, 0, -1)
            # Set annotated_index to -1
            struct.pack_into('i', self._shm.buf, 12, -1)
            self._owns_shm = True

        self._shm_name = self._shm.name
        self._ctrl_size = total_ctrl

        # Numpy views into frame data (after control block)
        self.frames = [
            np.ndarray(
                (height, width, channels),
                dtype=np.uint8,
                buffer=self._shm.buf,
                offset=total_ctrl + i * self.frame_size
            )
            for i in range(num_slots)
        ]

        if self._owns_shm:
            self.logger.info(
                f"Shared memory created: {num_slots} slots × "
                f"{width}×{height}×{channels} = {total_bytes / 1024 / 1024:.1f} MB "
                f"(name={self._shm_name})"
            )

    @property
    def shm_name(self) -> str:
        return self._shm_name

    # ── Control block helpers ─────────────────────────────────────

    def _get_latest_index(self) -> int:
        return struct.unpack_from('i', self._shm.buf, 0)[0]

    def _set_latest_index(self, idx: int):
        struct.pack_into('i', self._shm.buf, 0, idx)

    def _get_frame_counter(self) -> int:
        return struct.unpack_from('Q', self._shm.buf, 4)[0]

    def _incr_frame_counter(self) -> int:
        val = self._get_frame_counter() + 1
        struct.pack_into('Q', self._shm.buf, 4, val)
        return val

    def _get_annotated_index(self) -> int:
        return struct.unpack_from('i', self._shm.buf, 12)[0]

    def _set_annotated_index(self, idx: int):
        struct.pack_into('i', self._shm.buf, 12, idx)

    def _get_timestamp(self, slot: int) -> float:
        return struct.unpack_from('d', self._shm.buf, CTRL_HEADER_SIZE + slot * 8)[0]

    def _set_timestamp(self, slot: int, ts: float):
        struct.pack_into('d', self._shm.buf, CTRL_HEADER_SIZE + slot * 8, ts)

    # ── Writer API (capture process) ──────────────────────────────

    def write_frame(self, frame: np.ndarray) -> int:
        """Write a frame into the next slot. Returns the slot index."""
        frame_id = self._incr_frame_counter()
        # Use slots 0..num_slots-2 for capture (reserve last for annotated)
        usable_slots = max(1, self.num_slots - 1)
        slot = (frame_id - 1) % usable_slots

        # Resize if needed
        h, w = frame.shape[:2]
        if h != self.height or w != self.width:
            import cv2
            frame = cv2.resize(frame, (self.width, self.height))

        if frame.ndim == 2:
            frame = np.stack([frame] * self.channels, axis=-1)

        np.copyto(self.frames[slot], frame)
        self._set_timestamp(slot, time.time())
        self._set_latest_index(slot)

        return slot

    # ── Reader API (AI / display) ─────────────────────────────────

    def read_latest(self) -> Optional[Tuple[np.ndarray, float, int]]:
        """Get a numpy VIEW of the latest frame. Call .copy() if modifying."""
        idx = self._get_latest_index()
        if idx < 0:
            return None
        ts = self._get_timestamp(idx)
        fid = self._get_frame_counter()
        return self.frames[idx], ts, fid

    def read_latest_copy(self) -> Optional[Tuple[np.ndarray, float, int]]:
        """Get a COPY of the latest frame (safe to modify)."""
        result = self.read_latest()
        if result is None:
            return None
        frame, ts, fid = result
        return frame.copy(), ts, fid

    # ── Annotated frame API ───────────────────────────────────────

    def write_annotated(self, frame: np.ndarray) -> int:
        """Write annotated frame to the last slot."""
        slot = self.num_slots - 1
        h, w = frame.shape[:2]
        if h != self.height or w != self.width:
            import cv2
            frame = cv2.resize(frame, (self.width, self.height))
        np.copyto(self.frames[slot], frame)
        self._set_timestamp(slot, time.time())
        self._set_annotated_index(slot)
        return slot

    def read_annotated(self) -> Optional[Tuple[np.ndarray, float]]:
        """Read the latest annotated frame (view)."""
        idx = self._get_annotated_index()
        if idx < 0:
            return None
        ts = self._get_timestamp(idx)
        return self.frames[idx], ts

    # ── Properties ────────────────────────────────────────────────

    @property
    def latest_frame_id(self) -> int:
        return self._get_frame_counter()

    @property
    def latest_slot(self) -> int:
        return self._get_latest_index()

    # ── Cleanup ───────────────────────────────────────────────────

    def close(self):
        """Release shared memory."""
        try:
            self._shm.close()
            if self._owns_shm:
                self._shm.unlink()
            self.logger.info("Shared memory released")
        except Exception as e:
            self.logger.warning(f"Shared memory cleanup: {e}")
