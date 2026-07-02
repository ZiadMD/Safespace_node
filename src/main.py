"""
Safespace Node - Main Orchestrator.

Wires together:
    InputManager   (camera/video → buffer)
    AIManager      (buffer → inference → detection callbacks)
    OutputManager  (display GUI — lanes, speed, accident alert)
    NetworkManager (central unit — heartbeats, accident reports, commands)
"""
import sys
import os
import signal
import argparse
import time

from utils.config import Config
from utils.logger import Logger
from utils import restart_manager
from handlers.frame_buffer import FrameBuffer
from managers.input import InputManager
from managers.ai import AIManager
from managers.output import OutputManager
from managers.network import NetworkManager
from managers.stream import StreamManager
from managers.config_manager import ConfigManager
from handlers.gps_handler import GPSHandler


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
        '--no-ai',
        action='store_true',
        help='Disable AI detection (run without model inference)'
    )
    parser.add_argument(
        '--no-display',
        action='store_true',
        help='Run headless without the GUI display'
    )
    parser.add_argument(
        '--no-network',
        action='store_true',
        help='Disable network communication with central unit'
    )
    parser.add_argument(
        '--no-stream',
        action='store_true',
        help='Disable RTSP streaming (overrides stream.enabled in config)'
    )
    return parser.parse_args()


class SafespaceNode:
    """
    Safespace Node Orchestrator.

    Lifecycle:
        1. Config + Logger
        2. FrameBuffer (shared)
        3. OutputManager  → display GUI (lanes, speed, accident alert, dev feeds)
        4. NetworkManager → central unit (heartbeats, accident reports, commands)
        5. InputManager   → fills buffer from camera/video, pushes to display
        6. AIManager      → pulls from buffer, runs models, fires callbacks
    """

    def __init__(self, video_path: str = None, enable_ai: bool = True,
                 enable_display: bool = True, enable_network: bool = True,
                 enable_stream: bool = True):
        # 1. Configuration & Logging
        self.config = Config()
        Logger.setup(self.config.get('logging', {}))
        self.logger = Logger("SafespaceNode")
        self.logger.info("Initializing Safespace Node...")

        # Restart-marker detection — must happen as early as possible, right
        # after logging is up, so we know whether this boot followed a
        # deliberate CU-driven config restart (vs. a normal boot or crash).
        m = restart_manager.read_marker()
        if m:
            self.logger.info(
                f"Restarted deliberately into config v{m.get('new_config_version')} "
                f"(request_id={m.get('request_id')}, initiated_by={m.get('initiated_by')}, "
                f"attempt={m.get('attempt')}, status={m.get('status')})"
            )
            if m.get("initiated_by") == "debug":
                # Phase 1 self-test marker — no lifecycle owner, clear now.
                restart_manager.clear_marker()
            # else: a "cu"-initiated marker stays on disk — ConfigManager
            # (constructed below) takes ownership and clears/rewrites it
            # once the post-restart health gate resolves.
        else:
            self.logger.debug("Normal startup — no restart marker present")

        # Check camera mode — only on-chip IMX500 inference disables software AI
        camera_model = self.config.get('camera.model', 'imx500-raw')
        if camera_model == 'imx500':
            self.logger.info("IMX500 mode detected — disabling software AI (using on-chip inference)")
            enable_ai = False
        # imx500-raw uses the IMX500 sensor as a plain camera; software AI stays enabled

        if video_path:
            self.logger.info(f"Video test mode: {video_path}")
        if not enable_ai:
            self.logger.info("AI detection disabled")
        if not enable_display:
            self.logger.info("Display disabled (headless mode)")
        if not enable_network:
            self.logger.info("Network disabled (offline mode)")

        # 2. GPS Handler
        self.gps = GPSHandler(self.config)
        self.gps.start()

        # 3. Shared Frame Buffer
        self.buffer = FrameBuffer(self.config)

        # 4. Stream Manager (RTSP — MediaMTX + ffmpeg)
        self.stream = None
        stream_enabled = enable_stream and self.config.get_bool('stream.enabled', False)
        if stream_enabled:
            self.stream = StreamManager(self.config, self.buffer)
            self.logger.info("RTSP streaming enabled")
        else:
            self.logger.info("RTSP streaming disabled")

        # 6. Output Manager + Display (initialised early so callbacks can reference it)
        self.output = None
        if enable_display:
            self.output = OutputManager(
                self.config,
                on_manual_trigger=self._on_manual_trigger,
            )

        # 7. Network Manager (central unit communication)
        self.network = None
        if enable_network:
            self.network = NetworkManager(
                self.config,
                on_road_update=self.output.apply_road_update if self.output else None,
                on_accident_cleared=self.output.clear_accident if self.output else None,
            )

        # Attach GPS to network manager (heartbeat coordinates) and to the
        # output manager (so the GUI GPS indicator reflects live fix status).
        if self.network:
            self.network.set_gps_handler(self.gps)
        if self.output:
            self.output.set_gps_handler(self.gps)

        # 7b. Config Manager (CU-driven config updates over a dedicated WS) —
        # shares the network on/off switch, since it's CU communication too.
        self.config_manager = None
        if enable_network:
            self.config_manager = ConfigManager(
                self.config,
                on_restart_requested=self._restart_for_config_update,
            )

        # 8. Input Manager (camera or video → buffer)
        self.input = InputManager(
            self.config,
            self.buffer,
            video_path=video_path,
            on_frame=self.output.push_input_frame if self.output else None,
            on_imx500_detection=self._on_imx500_detection if camera_model == 'imx500' else None,
        )

        # 9. AI Manager (buffer → inference → callbacks)
        self.ai = None
        if enable_ai:
            self.ai = AIManager(
                self.config,
                self.buffer,
                on_detection=self._on_ai_detection,
                on_frame_processed=self.output.push_ai_frame if self.output else None,
            )
            self.logger.info(f"AI Manager ready — models: {self.ai.loaded_models}")

        # Lifecycle
        self.running = False
        self._setup_signals()

    def _setup_signals(self):
        """Handle OS signals for graceful shutdown."""
        def handler(sig, frame):
            self.logger.info("Shutdown signal received")
            self.stop()
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

        # DEBUG (Phase 1 restart-primitive test) — opt-in via
        # SAFESPACE_DEBUG_RESTART=1. Exercises write-marker -> re-exec ->
        # boot-detects-marker end-to-end. Remove once the CU-driven config
        # channel (Phase 2+) supersedes it as the real trigger.
        if os.environ.get("SAFESPACE_DEBUG_RESTART") == "1":
            def debug_restart_handler(sig, frame):
                self.logger.warning("DEBUG: SIGUSR1 received - triggering test restart")
                restart_manager.write_marker(
                    new_config_version="debug-test",
                    previous_config_backup_path="",
                    initiated_by="debug",
                )
                self.stop()
                restart_manager.restart_process(self.logger)
            signal.signal(signal.SIGUSR1, debug_restart_handler)
            self.logger.info("DEBUG restart trigger armed (SIGUSR1)")

    def start(self):
        """Start all services and enter the main loop."""
        self.logger.info("Starting Safespace Node...")

        # Start input pipeline
        if not self.input.start():
            self.logger.error("Input source failed to start — exiting")
            return

        # Start AI inference loop
        if self.ai:
            self.ai.start()

        # Start RTSP stream (MediaMTX + ffmpeg)
        if self.stream:
            self.stream.start()

        # Start network (heartbeats + socket connections)
        if self.network:
            self.network.start()

        # Start the config channel (independent of the command WS/heartbeat)
        if self.config_manager:
            self.config_manager.start()

        # Post-restart health gate — only runs when this boot followed a
        # CU-driven config restart (has_pending_marker is False on a normal
        # boot, so this is a no-op / zero added delay in the common case).
        if self.config_manager and self.config_manager.has_pending_marker:
            healthy, reason = self._run_health_gate()
            self.config_manager.report_health(healthy, reason)

        self.running = True
        self.logger.info("Safespace Node is running.")

        if self.output:
            # Display event loop BLOCKS — runs on the main thread.
            # Input and AI run in their own background threads.
            self.logger.info("Starting display (Qt event loop)...")
            self.output.start()
            # When the window is closed, Qt returns here — shut down.
            self.stop()
        else:
            # Headless mode — simple loop
            self.logger.info("Headless mode. Press Ctrl+C to stop.")
            try:
                while self.running:
                    if not self.input.is_running:
                        self.logger.info("Input source stopped — shutting down")
                        break
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
            finally:
                self.stop()

    def stop(self):
        """Cleanly shutdown all services."""
        if not self.running:
            return
        self.running = False
        self.logger.info("Stopping Safespace Node...")

        if self.ai:
            self.ai.stop()
        if self.stream:
            self.stream.stop()
        if self.config_manager:
            self.config_manager.stop()
        if self.network:
            self.network.stop()
        self.input.stop()
        if self.gps:
            self.gps.stop()

        self.logger.info("Safespace Node stopped.")

    def _restart_for_config_update(self):
        """Callback for ConfigManager: clean shutdown, then re-exec in place."""
        self.logger.info("Config update triggered restart — shutting down cleanly...")
        self.stop()
        restart_manager.restart_process(self.logger)

    def _run_health_gate(self, timeout: float = 15.0):
        """
        Concrete post-config-restart health definition:
            - input pipeline is running (camera/video opened for the
              configured mode)
            - if network is enabled, CU registration succeeded
        Polls up to `timeout` seconds since registration happens
        asynchronously relative to input startup. Returns (healthy, reason).
        """
        self.logger.info("Running post-restart health gate...")
        deadline = time.time() + timeout
        while time.time() < deadline:
            input_ok = self.input.is_running if self.input else False
            network_ok = self.network.registration_ok if self.network else True
            if input_ok and network_ok:
                return True, ""
            time.sleep(0.5)

        reasons = []
        if not (self.input.is_running if self.input else False):
            reasons.append("input pipeline not running")
        if self.network and not self.network.registration_ok:
            reasons.append("CU registration failed")
        return False, ("; ".join(reasons) or "health gate timed out")

    # ── Callbacks ─────────────────────────────────────────────────

    def _on_ai_detection(self, model_name: str, detections, frame):
        """
        Called by AIManager when a model produces detections.

        Args:
            model_name: Name of the model (e.g. "accident_detection")
            detections: supervision.Detections object
            frame: The frame where detection occurred
        """
        self.logger.warning(
            f"AI DETECTION [{model_name}]: {len(detections)} object(s) detected"
        )

        # Update the display with the accident
        if self.output:
            self.output.on_accident_detected(model_name, detections, frame)

        # Report to central unit
        if self.network:
            self.network.report_accident(detections, frame)

    def _on_imx500_detection(self, model_name: str, detections: dict, frame):
        """
        Called by InputManager when IMX500 produces detections.

        Args:
            model_name: "imx500"
            detections: Dict with keys: boxes, scores, class_ids
            frame: The frame where detection occurred
        """
        import numpy as np
        import supervision as sv
        
        num_detections = len(detections.get("boxes", [])) if detections else 0
        if num_detections > 0:
            orig_h, orig_w = frame.shape[:2]
            boxes = np.array(detections["boxes"])
            # Assuming imx500 boxes are [ymin, xmin, ymax, xmax] normalized if <= 1.0
            if boxes.max() <= 1.0:
                xyxy = np.zeros_like(boxes)
                xyxy[:, 0] = boxes[:, 1] * orig_w # xmin
                xyxy[:, 1] = boxes[:, 0] * orig_h # ymin
                xyxy[:, 2] = boxes[:, 3] * orig_w # xmax
                xyxy[:, 3] = boxes[:, 2] * orig_h # ymax
            else:
                # Absolute [xmin, ymin, xmax, ymax]
                xyxy = boxes

            sv_detections = sv.Detections(
                xyxy=xyxy,
                confidence=np.array(detections["scores"]),
                class_id=np.array(detections["class_ids"]).astype(int)
            )

            # IMX500 returns zero-padded tensors (e.g. 300 boxes). Filter by confidence.
            conf_thresh = self.config.get_float('camera.imx500.confidence', 0.5)
            mask = sv_detections.confidence >= conf_thresh
            sv_detections = sv_detections[mask]

            if len(sv_detections) > 0:
                self.logger.warning(
                    f"IMX500 DETECTION: {len(sv_detections)} object(s) detected"
                )
                box_annotator = sv.BoxAnnotator(thickness=2)
                label_annotator = sv.LabelAnnotator(text_scale=0.5, text_thickness=1)
                
                labels = [f"class_{c} {conf:.2f}" for c, conf in zip(sv_detections.class_id, sv_detections.confidence)]
                annotated = box_annotator.annotate(frame.copy(), sv_detections)
                annotated = label_annotator.annotate(annotated, sv_detections, labels)

                if self.output:
                    self.output.on_imx500_detected(sv_detections, annotated)

                if self.network:
                    self.network.report_accident(sv_detections, frame)
            else:
                if self.output:
                    self.output.on_imx500_detected(None, frame)
        else:
            if self.output:
                self.output.on_imx500_detected(None, frame)

    def _on_manual_trigger(self):
        """Called when the user presses SPACE on the display."""
        self.logger.info("Manual accident report triggered by user!")
        if self.output:
            self.output.trigger_accident_alert()


if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    args = parse_args()
    node = SafespaceNode(
        video_path=args.video,
        enable_ai=not args.no_ai,
        enable_display=not args.no_display,
        enable_network=not args.no_network,
        enable_stream=not args.no_stream,
    )
    node.start()
