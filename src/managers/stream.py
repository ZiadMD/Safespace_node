"""
Stream Manager — Manages the MediaMTX subprocess and the RTSP stream handler.

Responsibilities:
    - Launch MediaMTX as a child process (serves RTSP on port 8554)
    - Start StreamHandler (pushes frames from FrameBuffer to MediaMTX via ffmpeg)
    - Clean shutdown of both on stop()

Central Unit pulls the stream from:
    rtsp://<node-ip>:<stream.port>/<stream.path>   (default: rtsp://<ip>:8554/live)
"""
import time
import subprocess
from pathlib import Path
from typing import Optional

from utils.config import Config
from utils.logger import Logger
from handlers.frame_buffer import FrameBuffer
from handlers.stream_handler import StreamHandler


class StreamManager:
    """
    Owns the MediaMTX process and the FFmpeg→RTSP stream pipeline.

    Usage (from main.py):
        stream = StreamManager(config, buffer)
        stream.start()
        # ... node runs ...
        stream.stop()
    """

    # Seconds to wait for MediaMTX to be ready before starting ffmpeg
    _MEDIAMTX_BOOT_WAIT = 1.5

    def __init__(self, config: Config, buffer: FrameBuffer):
        self.logger = Logger("StreamManager")
        self.config = config

        self._handler = StreamHandler(config, buffer)

        # MediaMTX binary + config paths (resolved relative to project root)
        project_root = Path(__file__).parent.parent.parent
        mediamtx_bin = config.get('stream.mediamtx_path', 'mediamtx')
        mediamtx_cfg = config.get('stream.mediamtx_config', 'configs/mediamtx.yml')

        self._mediamtx_bin: str = mediamtx_bin
        self._mediamtx_cfg: Path = project_root / mediamtx_cfg
        self._mediamtx_process: Optional[subprocess.Popen] = None

    # ── Lifecycle ─────────────────────────────────────────────────

    def start(self):
        self.logger.info("Starting Stream Manager...")
        if not self._start_mediamtx():
            self.logger.error(
                "MediaMTX failed to start — RTSP stream disabled. "
                "Download the binary from https://github.com/bluenviron/mediamtx/releases "
                "and place it on PATH or set stream.mediamtx_path in config.yaml."
            )
            return
        # Give MediaMTX a moment to open its RTSP port before ffmpeg connects
        time.sleep(self._MEDIAMTX_BOOT_WAIT)
        self._handler.start()
        self.logger.info(
            f"Streaming live at {self._handler.rtsp_url}  "
            f"(Central Unit pulls from rtsp://<node-ip>:{self.config.get_int('stream.port', 8554)}"
            f"/{self.config.get('stream.path', 'live')})"
        )

    def stop(self):
        self.logger.info("Stopping Stream Manager...")
        self._handler.stop()
        self._stop_mediamtx()
        self.logger.info("Stream Manager stopped")

    # ── MediaMTX ─────────────────────────────────────────────────

    def _start_mediamtx(self) -> bool:
        if not self._mediamtx_cfg.exists():
            self.logger.error(
                f"MediaMTX config not found: {self._mediamtx_cfg}. "
                "Create configs/mediamtx.yml or set stream.mediamtx_config in config.yaml."
            )
            return False

        try:
            self._mediamtx_process = subprocess.Popen(
                [self._mediamtx_bin, str(self._mediamtx_cfg)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self.logger.info(
                f"MediaMTX started (pid={self._mediamtx_process.pid}, "
                f"config={self._mediamtx_cfg})"
            )
            return True
        except FileNotFoundError:
            self.logger.error(
                f"mediamtx binary not found at '{self._mediamtx_bin}'. "
                "Download the latest release from "
                "https://github.com/bluenviron/mediamtx/releases "
                "and place it in your PATH or set stream.mediamtx_path in config.yaml."
            )
            return False
        except Exception as e:
            self.logger.error(f"MediaMTX failed to start: {e}")
            return False

    def _stop_mediamtx(self):
        if self._mediamtx_process is None:
            return
        try:
            self._mediamtx_process.terminate()
            self._mediamtx_process.wait(timeout=3)
        except Exception:
            try:
                self._mediamtx_process.kill()
            except Exception:
                pass
        self._mediamtx_process = None
        self.logger.info("MediaMTX stopped")

    # ── Properties ────────────────────────────────────────────────

    @property
    def is_streaming(self) -> bool:
        return self._handler.is_streaming

    @property
    def rtsp_url(self) -> str:
        return self._handler.rtsp_url
