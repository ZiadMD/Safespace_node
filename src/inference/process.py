"""
Inference Process — runs AI models in its own OS process.

Reads frames from shared memory, runs inference, publishes detections
to the message bus. Sends health pings so the supervisor knows it's alive.
"""
import time
import signal
import multiprocessing as mp
from typing import Optional, Dict, Any, List
from pathlib import Path

from core.config import Config
from core.logger import Logger
from core.shared_memory import SharedFrameSlots
from core.message_bus import MessageBus
from core.constants import TOPIC_DETECTION, TOPIC_FRAME_ANNOTATED, TOPIC_AI_HEALTH
from inference.model_loader import ModelLoader
from inference.model_runner import ModelRunner


def inference_process_entry(
    config_path: str,
    shm_name: str,
    width: int,
    height: int,
    channels: int,
    num_slots: int,
    bus: MessageBus,
    stop_event: Optional[mp.Event] = None,
):
    """
    Entry point for the AI inference subprocess.

    Loads models, pulls frames from shared memory, runs inference,
    publishes detections and annotated frames via the message bus.
    """
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    logger = Logger("InferenceProcess")
    config = Config(config_path)
    Logger.setup(config.get('logging', {}))

    # Attach to shared memory
    slots = SharedFrameSlots(width, height, channels, num_slots, shm_name=shm_name)

    # Load models
    loader = ModelLoader()
    runner = ModelRunner()
    models = _load_models(config, loader, logger)

    if not models:
        logger.warning("No models loaded — inference process exiting")
        return

    # Warm-up pass (eliminates first-frame latency spike)
    _warmup_models(models, runner, width, height, logger)

    logger.info(f"Inference process started — models: {list(models.keys())}")
    last_frame_id = -1
    health_ping_interval = 5.0
    last_health_ping = 0.0

    try:
        while not (stop_event and stop_event.is_set()):
            result = slots.read_latest()

            if result is None:
                time.sleep(0.01)
                continue

            frame, timestamp, frame_id = result

            # Skip already-processed frames
            if frame_id <= last_frame_id:
                time.sleep(0.005)
                continue
            last_frame_id = frame_id

            # Run each model
            annotated = frame.copy()
            any_detections = False

            for model_name, model_data in models.items():
                detections = runner.detect(
                    model=model_data["model"],
                    frame=frame,
                    confidence=model_data["confidence"],
                    target_classes=model_data["target_classes"],
                )

                if len(detections) > 0:
                    any_detections = True
                    annotated = runner.annotate(annotated, detections, model_data["model"])

                    # Publish detection event
                    bus.publish(TOPIC_DETECTION, {
                        "model_name": model_name,
                        "num_detections": len(detections),
                        "frame_id": frame_id,
                        "timestamp": timestamp,
                        "xyxy": detections.xyxy.tolist(),
                        "confidence": detections.confidence.tolist(),
                        "class_id": detections.class_id.tolist(),
                    })

            # Write annotated frame to shared memory
            slots.write_annotated(annotated)
            bus.publish(TOPIC_FRAME_ANNOTATED, {
                "frame_id": frame_id,
                "timestamp": time.time(),
                "has_detections": any_detections,
            })

            # Health ping to supervisor
            now = time.time()
            if now - last_health_ping > health_ping_interval:
                bus.publish(TOPIC_AI_HEALTH, {
                    "time": now,
                    "frame_id": frame_id,
                    "models": list(models.keys()),
                })
                last_health_ping = now

    except Exception as e:
        logger.error(f"Inference process error: {e}")
    finally:
        loader.unload_all()
        logger.info("Inference process stopped")


def _load_models(config: Config, loader: ModelLoader, logger: Logger) -> Dict[str, Dict[str, Any]]:
    """Load all enabled models from config."""
    models_config = config.get("ai.models", {})
    result = {}

    for name, conf in models_config.items():
        if not conf.get("enabled", False):
            continue

        model_path = conf.get("path")
        if not model_path:
            continue

        base_dir = Path(__file__).parent.parent.parent
        resolved = str(base_dir / model_path)
        model = loader.load(resolved)

        if model is None:
            logger.error(f"Failed to load model '{name}' from {resolved}")
            continue

        result[name] = {
            "model": model,
            "confidence": conf.get("confidence", 0.5),
            "target_classes": conf.get("target_classes", []),
        }
        logger.info(
            f"Model '{name}' ready (conf={conf.get('confidence', 0.5)}, "
            f"classes={conf.get('target_classes', [])})"
        )

    return result


def _warmup_models(models: dict, runner: ModelRunner, width: int, height: int, logger: Logger):
    """Run a dummy inference pass on each model to eliminate first-frame latency."""
    import numpy as np
    dummy = np.zeros((height, width, 3), dtype=np.uint8)

    for name, data in models.items():
        try:
            logger.info(f"Warming up model '{name}'...")
            runner.detect(
                model=data["model"],
                frame=dummy,
                confidence=data["confidence"],
                target_classes=data["target_classes"],
                use_tracking=False,
            )
            logger.info(f"Model '{name}' warm-up complete")
        except Exception as e:
            logger.warning(f"Warm-up failed for '{name}': {e}")
