"""
Capture Process — runs in its own OS process for GIL-free frame capture.

Reads frames from the camera/video source and writes them into
shared memory. Publishes "frame.captured" events to the message bus.
"""
import time
import signal
import multiprocessing as mp
from typing import Optional

from core.config import Config
from core.logger import Logger
from core.shared_memory import SharedFrameSlots
from core.message_bus import MessageBus
from core.constants import TOPIC_FRAME_CAPTURED, TOPIC_SHUTDOWN
from capture.sources import create_source


def capture_process_entry(
    config_path: str,
    shm_name: str,
    width: int,
    height: int,
    channels: int,
    num_slots: int,
    bus: MessageBus,
    video_path: Optional[str] = None,
    stop_event: Optional[mp.Event] = None,
):
    """
    Entry point for the capture subprocess.

    Args:
        config_path: Path to the YAML config file.
        shm_name: Name of the shared memory block to attach to.
        width, height, channels, num_slots: Frame dimensions and slot count.
        bus: The MessageBus instance (shared via fork).
        video_path: Optional video file path (for testing).
        stop_event: Event to signal shutdown.
    """
    # Ignore SIGINT in child — let the parent handle it
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    logger = Logger("CaptureProcess")
    config = Config(config_path)
    Logger.setup(config.get('logging', {}))

    # Attach to existing shared memory
    slots = SharedFrameSlots(width, height, channels, num_slots, shm_name=shm_name)

    # Create input source
    source = create_source(config, video_path)
    if not source.start():
        logger.error("Failed to start input source — capture process exiting")
        return

    target_fps = config.get_int('camera.fps', 30)
    frame_interval = 1.0 / target_fps if target_fps > 0 else 0.033

    logger.info(f"Capture process started (source={type(source).__name__}, fps={target_fps})")

    try:
        while not (stop_event and stop_event.is_set()):
            loop_start = time.monotonic()

            frame = source.read_frame()

            if frame is not None:
                slot = slots.write_frame(frame)
                bus.publish(TOPIC_FRAME_CAPTURED, {
                    "slot": slot,
                    "timestamp": time.time(),
                    "frame_id": slots.latest_frame_id,
                })
            else:
                if not source.is_running:
                    logger.info("Input source ended")
                    break
                time.sleep(0.01)
                continue

            # FPS throttle
            elapsed = time.monotonic() - loop_start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    except Exception as e:
        logger.error(f"Capture process error: {e}")
    finally:
        source.stop()
        logger.info("Capture process stopped")
