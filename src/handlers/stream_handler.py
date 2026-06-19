"""
Stream Handler — Pulls raw frames from FrameBuffer and pushes them to
a local MediaMTX RTSP server via an ffmpeg subprocess.

Pipeline:
    FrameBuffer --get_latest()--> StreamHandler --pipe--> ffmpeg --> MediaMTX (RTSP)

ffmpeg is restarted automatically on crash with exponential backoff.
"""
import time
import subprocess
import threading
from pathlib import Path
from typing import Optional

import cv2

from utils.config import Config
from utils.logger import Logger
from handlers.frame_buffer import FrameBuffer


class StreamHandler:
    """
    Reads frames from FrameBuffer and streams them to MediaMTX via ffmpeg.

    ffmpeg receives raw BGR frames on stdin and publishes H.264 RTSP to
    rtsp://localhost:<port>/<path>.
    """

    _RECONNECT_DELAY_MIN = 2
    _RECONNECT_DELAY_MAX = 30

    def __init__(self, config: Config, buffer: FrameBuffer):
        self.logger = Logger("StreamHandler")
        self._buffer = buffer

        self._fps: int = config.get_int('stream.fps', 15)
        self._width: int = config.get_int('stream.width', 640)
        self._height: int = config.get_int('stream.height', 640)
        port: int = config.get_int('stream.port', 8554)
        path: str = config.get('stream.path', 'live')
        self._rtsp_url: str = f"rtsp://localhost:{port}/{path}"

        self._process: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._reconnect_delay = self._RECONNECT_DELAY_MIN

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._stream_loop,
            name="RTSPStream",
            daemon=True,
        )
        self._thread.start()
        self.logger.info(f"Stream handler started → {self._rtsp_url}")

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._kill_ffmpeg()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self.logger.info("Stream handler stopped")

    # ── Stream loop ───────────────────────────────────────────────

    def _stream_loop(self):
        frame_interval = 1.0 / self._fps
        last_timestamp = 0.0

        while self._running:
            # (Re)start ffmpeg if not running
            if self._process is None or self._process.poll() is not None:
                self.logger.info(f"Starting ffmpeg (retry delay={self._reconnect_delay}s)...")
                self._start_ffmpeg()
                if self._process is None:
                    time.sleep(self._reconnect_delay)
                    self._reconnect_delay = min(
                        self._reconnect_delay * 2, self._RECONNECT_DELAY_MAX
                    )
                    continue
                self._reconnect_delay = self._RECONNECT_DELAY_MIN

            loop_start = time.monotonic()

            result = self._buffer.get_latest_with_timestamp()
            if result is None:
                time.sleep(0.01)
                continue

            frame, timestamp = result

            # Skip duplicate frames
            if timestamp <= last_timestamp:
                time.sleep(0.005)
                continue
            last_timestamp = timestamp

            # Resize only when stream resolution differs from capture resolution
            h, w = frame.shape[:2]
            if w != self._width or h != self._height:
                frame = cv2.resize(frame, (self._width, self._height))

            try:
                self._process.stdin.write(frame.tobytes())
            except (BrokenPipeError, OSError):
                self.logger.warning("FFmpeg pipe broken — will restart")
                self._kill_ffmpeg()
                continue

            # FPS throttle
            elapsed = time.monotonic() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    # ── FFmpeg management ─────────────────────────────────────────

    def _build_ffmpeg_cmd(self):
        return [
            'ffmpeg', '-y',
            '-f', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', f'{self._width}x{self._height}',
            '-r', str(self._fps),
            '-i', 'pipe:0',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-pix_fmt', 'yuv420p',
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            self._rtsp_url,
        ]

    def _start_ffmpeg(self):
        try:
            self._process = subprocess.Popen(
                self._build_ffmpeg_cmd(),
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logger.info(f"FFmpeg started (pid={self._process.pid})")
        except FileNotFoundError:
            self.logger.error(
                "ffmpeg not found. Install it with: sudo apt install ffmpeg"
            )
            self._process = None
        except Exception as e:
            self.logger.error(f"FFmpeg start failed: {e}")
            self._process = None

    def _kill_ffmpeg(self):
        if self._process is None:
            return
        try:
            self._process.stdin.close()
        except Exception:
            pass
        try:
            self._process.terminate()
            self._process.wait(timeout=2)
        except Exception:
            try:
                self._process.kill()
            except Exception:
                pass
        self._process = None

    # ── Properties ────────────────────────────────────────────────

    @property
    def is_streaming(self) -> bool:
        return self._running and self._process is not None and self._process.poll() is None

    @property
    def rtsp_url(self) -> str:
        return self._rtsp_url
