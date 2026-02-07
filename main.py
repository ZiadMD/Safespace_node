"""
Safespace Node — Entry Point

Pipeline + Event Bus architecture:
    CaptureStage → [frame_queue] → InferenceStage → [detection_queue] → DecisionStage
                                                                            ↕ EventBus
                                                            NetworkWorker ← AccidentDetected
                                                          DisplaySubscriber ← DisplayUpdate
"""
import sys
import signal
import argparse
from queue import Queue
from threading import Event

from utils.config import Config
from utils.logger import Logger

from core.bus import EventBus
from core.events import ManualTrigger, ShutdownRequested


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Safespace Node - Road Safety Monitoring System")
    parser.add_argument(
        '--video', '-v',
        type=str,
        default=None,
        help='Path to video file for testing (bypasses camera)'
    )
    parser.add_argument(
        '--offline', '-o',
        action='store_true',
        help='Run in offline mode (skip network connection)'
    )
    parser.add_argument(
        '--no-ai',
        action='store_true',
        help='Disable AI detection (run without model inference)'
    )
    return parser.parse_args()


class SafespaceNode:
    """
    Safespace Node Orchestrator (Pipeline + Event Bus architecture).
    
    Wires together:
      - Pipeline stages (Capture → Inference → Decision) via bounded Queues
      - Event bus subscribers (NetworkWorker, DisplaySubscriber) via EventBus
      - Display (PyQt6, blocks on main thread)
    
    No direct callbacks between components. No shared mutable state.
    """

    def __init__(self, video_path: str = None, offline: bool = False, enable_ai: bool = True):
        # ── 1. Foundation ────────────────────────────────────────────
        self.config = Config()
        Logger.setup(self.config.get('logging', {}))
        self.logger = Logger("SafespaceNode")
        self.logger.info("Initializing Safespace Node (Pipeline + Event Bus)...")

        self.offline = offline
        self.enable_ai = enable_ai
        self.video_path = video_path

        # Shared shutdown signal — replaces os._exit()
        self.stop_event = Event()

        # Central event bus — replaces all callbacks
        self.bus = EventBus()

        # ── 2. Bounded Queues (pipeline backpressure) ────────────────
        self.frame_queue = Queue(maxsize=2)      # Drop-on-full in CaptureStage
        self.detection_queue = Queue(maxsize=5)   # Buffer between inference & decision

        # ── 3. Frame Source (Camera or Video) ────────────────────────
        if video_path:
            from Handlers.Video_Input_Handler import VideoInputHandler
            self.frame_source = VideoInputHandler(video_path)
            self.source_type = "video"
            self.logger.info(f"Video test mode: {video_path}")
        else:
            from Handlers.Camera_Handler import CameraHandler
            camera_conf = self.config.get('camera', {})
            self.frame_source = CameraHandler(camera_conf)
            self.source_type = "camera"

        # ── 4. AI Models (optional) ──────────────────────────────────
        self.models = {}
        self.detection_handler = None
        if enable_ai:
            self._load_ai_models()
        else:
            self.logger.info("AI detection disabled")

        # ── 5. Pipeline Stages ───────────────────────────────────────
        from core.stages.capture import CaptureStage
        fps = self.config.get_int('camera.fps', 30)
        loop_video = self.config.get_bool('camera.loop_video', True)

        self.capture_stage = CaptureStage(
            source=self.frame_source,
            out_queue=self.frame_queue,
            stop_event=self.stop_event,
            fps=fps,
            loop_video=loop_video,
            source_type=self.source_type,
        )

        self.inference_stage = None
        if enable_ai and self.models:
            from core.stages.inference import InferenceStage
            self.inference_stage = InferenceStage(
                in_queue=self.frame_queue,
                out_queue=self.detection_queue,
                stop_event=self.stop_event,
                models=self.models,
                detection_handler=self.detection_handler,
            )

        from core.stages.decision import DecisionStage
        self.decision_stage = DecisionStage(
            detection_queue=self.detection_queue,
            bus=self.bus,
            stop_event=self.stop_event,
            config=self.config,
        )

        # ── 6. Network Worker (bus subscriber) ───────────────────────
        self.network_worker = None
        if not offline:
            from core.network_worker import NetworkWorker
            self.network_worker = NetworkWorker(
                config=self.config,
                bus=self.bus,
                stop_event=self.stop_event,
            )
        else:
            self.logger.info("Offline mode — skipping network")

        # ── 7. Display + Display Subscriber ──────────────────────────
        from Handlers.Display_Handler import DisplayHandler
        from core.display_subscriber import DisplaySubscriber

        self.display = DisplayHandler(
            config=self.config,
            on_manual_trigger=self._on_manual_trigger,
            stop_event=self.stop_event,
        )
        self.display_subscriber = DisplaySubscriber(
            bus=self.bus,
            display=self.display,
        )

        # ── 8. OS Signals ────────────────────────────────────────────
        self._setup_signals()
        self.logger.info("Safespace Node initialized successfully")

    def _load_ai_models(self):
        """Load YOLO models from config."""
        from Handlers.Model_Loader_Handler import ModelLoader
        from Handlers.Model_Detection_Handler import ModelDetectionHandler

        loader = ModelLoader()
        self.detection_handler = ModelDetectionHandler()

        ai_config = self.config.get("ai", {})
        models_config = ai_config.get("models", {})

        for model_name, model_conf in models_config.items():
            if not model_conf.get("enabled", False):
                continue

            model_path = model_conf.get("path")
            if not model_path:
                continue

            model = loader.load_model(model_path)
            if model:
                self.models[model_name] = {
                    "model": model,
                    "confidence": model_conf.get("confidence", 0.5),
                    "classes": model_conf.get("classes", []),
                }
                self.logger.info(f"Loaded model: {model_name}")

        if self.models:
            self.logger.info(f"AI ready with {len(self.models)} model(s)")
        else:
            self.logger.warning("No AI models loaded")

    def _setup_signals(self):
        """Handle OS signals for graceful shutdown."""
        def handler(sig, frame):
            self.logger.info("Shutdown signal received")
            self.stop()
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def _on_manual_trigger(self):
        """Called by Qt keyPressEvent — publishes ManualTrigger to the bus."""
        self.bus.publish(ManualTrigger())

    def start(self):
        """Start all pipeline stages, workers, and enter the Qt event loop."""
        self.logger.info("Starting Safespace Node services...")

        # Start network (non-blocking)
        if self.network_worker:
            if not self.network_worker.start():
                self.logger.warning("Network failed — running in offline mode")

        # Start pipeline stages (background threads)
        self.capture_stage.start()
        if self.inference_stage:
            self.inference_stage.start()
        self.decision_stage.start()

        self.logger.info("Pipeline stages running")

        try:
            # Display blocks on the main thread (Qt event loop)
            self.display.start()
        except Exception as e:
            self.logger.error(f"Display error: {e}")
        finally:
            # Window closed or error — trigger full shutdown
            self.stop()

    def stop(self):
        """Gracefully shutdown all components."""
        if self.stop_event.is_set():
            return  # Already shutting down

        self.stop_event.set()
        self.logger.info("Stopping Safespace Node...")

        # Stop display
        if self.display:
            self.display.stop()

        # Stop network
        if self.network_worker:
            self.network_worker.stop()

        # Pipeline stages are daemon threads — they'll check stop_event and exit
        # But we join them for clean shutdown
        for stage in [self.capture_stage, self.inference_stage, self.decision_stage]:
            if stage and stage.is_alive():
                stage.join(timeout=2.0)

        # Clean up event bus
        self.bus.clear()

        self.logger.info("Safespace Node stopped successfully")


if __name__ == "__main__":
    args = parse_args()

    node = SafespaceNode(
        video_path=args.video,
        offline=args.offline,
        enable_ai=not args.no_ai,
    )
    node.start()
