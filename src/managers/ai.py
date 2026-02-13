"""
AI Manager — Pulls frames from the buffer, runs inference, and fires detection callbacks.

Architecture:
    [FrameBuffer] --get_latest()--> [AIManager] --detect()--> callback(model_name, detections, frame)

The AI Manager runs its own inference loop in a background thread.
It pulls frames from the buffer at whatever pace the GPU can handle,
so it naturally skips frames when inference is slower than camera FPS.
"""
import time
import threading
from typing import Optional, Callable, Dict, Any, List
from pathlib import Path

import supervision as sv
from cv2.typing import MatLike

from utils.config import Config
from utils.logger import Logger
from handlers.frame_buffer import FrameBuffer
from handlers.model_loader import ModelLoader
from handlers.model_detection import ModelDetection


# Type aliases
DetectionCallback = Callable[[str, sv.Detections, MatLike], None]
FrameCallback = Callable[[MatLike], None]


class AIManager:
    """
    Manages AI model lifecycle, inference loop, and detection events.

    Pulls the latest frame from the shared buffer, runs each loaded model,
    and fires callbacks when detections are found.
    """

    def __init__(
        self,
        config: Config,
        buffer: FrameBuffer,
        on_detection: Optional[DetectionCallback] = None,
        on_frame_processed: Optional[FrameCallback] = None,
        model_names: Optional[list] = None,
    ):
        """
        Args:
            config: Application configuration.
            buffer: Shared frame buffer to pull frames from.
            on_detection: Callback fired when a model produces detections.
                          Signature: (model_name: str, detections: sv.Detections, frame: MatLike)
            on_frame_processed: Callback fired every inference cycle with the
                                annotated frame (bounding boxes drawn).
                                Signature: (annotated_frame: MatLike)
            model_names: List of model keys to load from config (e.g. ["accident_detection"]).
                         If None, loads all enabled models.
        """
        self.logger = Logger("AIManager")
        self.config = config
        self.buffer = buffer
        self.on_detection = on_detection
        self.on_frame_processed = on_frame_processed

        self._loader = ModelLoader()
        self._detector = ModelDetection()

        # Supervision annotators for drawing bounding boxes
        self._box_annotator = sv.BoxAnnotator(thickness=2)
        self._label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)

        # Loaded model registry: { name: { model, confidence, target_classes, path } }
        self._models: Dict[str, Dict[str, Any]] = {}

        self._thread: Optional[threading.Thread] = None
        self._running = False

        # Load requested models
        self._load_models(model_names)

    # ── Model Loading ─────────────────────────────────────────────

    def _load_models(self, model_names: Optional[list] = None):
        """Load models from config based on provided names or all enabled."""
        models_config = self.config.get("ai.models", {})

        if model_names is None:
            # Load all enabled models
            names_to_load = [
                name for name, conf in models_config.items()
                if conf.get("enabled", False)
            ]
        else:
            if isinstance(model_names, str):
                model_names = [model_names]
            names_to_load = model_names

        for name in names_to_load:
            self._load_model(name, models_config.get(name, {}))

    def _load_model(self, name: str, model_conf: dict):
        """Load a single model by name and config."""
        if not model_conf:
            self.logger.warning(f"No config found for model '{name}', skipping")
            return

        if not model_conf.get("enabled", True):
            self.logger.info(f"Model '{name}' is disabled, skipping")
            return

        model_path = model_conf.get("path")
        if not model_path:
            self.logger.error(f"No path specified for model '{name}'")
            return

        # Resolve path relative to project root
        base_dir = Path(__file__).parent.parent.parent
        resolved_path = str(base_dir / model_path)

        model = self._loader.load(resolved_path)
        if model is None:
            self.logger.error(f"Failed to load model '{name}' from {resolved_path}")
            return

        self._models[name] = {
            "model": model,
            "path": resolved_path,
            "confidence": model_conf.get("confidence", 0.5),
            "target_classes": model_conf.get("target_classes", []),
        }
        self.logger.info(f"Model '{name}' ready (conf={model_conf.get('confidence', 0.5)}, "
                         f"classes={model_conf.get('target_classes', [])})")

    # ── Inference Loop ────────────────────────────────────────────

    def start(self):
        """Start the background inference loop."""
        if self._running:
            self.logger.warning("AI Manager already running")
            return

        if not self._models:
            self.logger.warning("No models loaded — AI Manager will not start")
            return

        self._running = True
        self._thread = threading.Thread(target=self._inference_loop, name="AIInference", daemon=True)
        self._thread.start()
        self.logger.info("AI inference loop started")

    def _inference_loop(self):
        """Pull latest frame from buffer, run all models, fire callbacks."""
        last_timestamp = 0.0

        while self._running:
            # Pull the latest frame
            result = self.buffer.get_latest_with_timestamp()

            if result is None:
                # Buffer empty — wait briefly
                time.sleep(0.01)
                continue

            frame, timestamp = result

            # Skip if we've already processed this exact frame
            if timestamp <= last_timestamp:
                time.sleep(0.005)
                continue
            last_timestamp = timestamp

            # Run each model on the frame
            annotated = frame.copy() if self.on_frame_processed else None

            for model_name, model_data in self._models.items():
                detections = self._detector.detect(
                    model=model_data["model"],
                    frame=frame,
                    confidence=model_data["confidence"],
                    target_classes=model_data["target_classes"],
                )

                # Draw annotations on the dev-feed frame
                if annotated is not None and len(detections) > 0:
                    model = model_data["model"]
                    labels = [
                        f"{model.names[c]} {conf:.2f}"
                        for c, conf in zip(detections.class_id, detections.confidence)
                    ]
                    annotated = self._box_annotator.annotate(annotated, detections)
                    annotated = self._label_annotator.annotate(annotated, detections, labels)

                if len(detections) > 0 and self.on_detection:
                    self.on_detection(model_name, detections, frame)

            # Push annotated frame to display (dev mode feed)
            if self.on_frame_processed and annotated is not None:
                self.on_frame_processed(annotated)

    def stop(self):
        """Stop the inference loop and unload models."""
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._loader.unload_all()
        self._models.clear()
        self.logger.info("AI Manager stopped")

    # ── Single-shot API (optional) ────────────────────────────────

    def detect_once(self, model_name: str, frame: MatLike) -> Optional[sv.Detections]:
        """
        Run a single inference on a specific frame (no loop needed).

        Args:
            model_name: Name of the loaded model to use.
            frame: The frame to analyze.

        Returns:
            Detections or None if model not found.
        """
        model_data = self._models.get(model_name)
        if not model_data:
            self.logger.error(f"Model '{model_name}' not loaded")
            return None

        return self._detector.detect(
            model=model_data["model"],
            frame=frame,
            confidence=model_data["confidence"],
            target_classes=model_data["target_classes"],
        )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def loaded_models(self) -> List[str]:
        return list(self._models.keys())
