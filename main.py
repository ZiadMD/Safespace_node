import sys
import os
import signal
import argparse
from typing import Dict, Any

from utils.config import Config
from utils.logger import Logger
from Managers.Network_Manager import NetworkManager
from Managers.IO_Manager import IOManager
from Managers.AI_Manger import AIManager


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
    Safespace Node Orchestrator.
    Manages the lifecycle and communication between Network, IO, and AI managers.
    """
    
    def __init__(self, video_path: str = None, offline: bool = False, enable_ai: bool = True):
        # 1. Load Granular Configuration
        self.config = Config()
        self.offline = offline
        self.enable_ai = enable_ai
        
        # 2. Setup Global Logging
        Logger.setup(self.config.get('logging', {}))
        
        self.logger = Logger("SafespaceNode")
        self.logger.info("Initializing Safespace Node...")
        
        if video_path:
            self.logger.info(f"Video test mode: {video_path}")
        if offline:
            self.logger.info("Offline mode enabled")
        if not enable_ai:
            self.logger.info("AI detection disabled")
        
        # 3. Initialize Managers
        self.network = NetworkManager(
            self.config, 
            on_central_unit_instruction=self._on_central_unit_instruction
        )
        
        self.io = IOManager(
            self.config, 
            on_manual_trigger=self._on_manual_accident_report,
            video_path=video_path
        )
        
        # 4. Initialize AI Manager (optional)
        self.ai = None
        if enable_ai:
            self.ai = AIManager(
                self.config,
                self.io,
                on_detection=self._on_ai_detection
            )
            self.logger.info("AI Manager initialized")
        
        # Lifecycle / Flow Management
        self.running = False
        self.awaiting_confirmation = False
        self._setup_signals()

    def _setup_signals(self):
        """Handle OS signals for graceful shutdown."""
        def handler(sig, frame):
            self.logger.info("Shutdown signal received")
            self.stop()
        signal.signal(signal.SIGINT, handler)
        signal.signal(signal.SIGTERM, handler)

    def start(self):
        """Start the node services and enter event loop."""
        self.logger.info("Starting Safespace Node services...")
        
        if not self.offline:
            if not self.network.start():
                self.logger.warning("Network starting failed - Node running in offline mode")
        else:
            self.logger.info("Skipping network connection (offline mode)")

        self.running = True
        
        try:
            self.io.start()
        except Exception as e:
            self.logger.error(f"IO Runtime error: {e}")
        finally:
            self.stop()

    def stop(self):
        """Cleanly shutdown all services."""
        if not self.running:
            return
            
        self.running = False
        self.logger.info("Stopping Safespace Node...")
        
        self.network.stop()
        self.io.stop()
        
        self.logger.info("Safespace Node stopped successfully.")

    def _on_manual_accident_report(self):
        """Callback for local manual trigger (e.g. Spacebar)."""
        if self.awaiting_confirmation:
            self.logger.warning("Ignored: Node is already awaiting action from the Central Unit.")
            return

        self.logger.info("User triggered a manual accident report. Transitioning to AWAITING state...")
        self.awaiting_confirmation = True
        
        # 1. Capture snapshot from the active camera
        snapshot_path = self.io.get_accident_snapshot()
        media = [snapshot_path] if snapshot_path else None
        
        # 2. Report to central unit through the network manager
        self.network.report_accident(lane_number="1", media=media)

    def _on_ai_detection(self, model_name: str, detections, frame):
        """
        Callback for AI detections (e.g., accident detected by model).
        
        Args:
            model_name: Name of the model that made the detection
            detections: Detection results from supervision
            frame: The frame where detection occurred
        """
        if self.awaiting_confirmation:
            self.logger.debug(f"AI detection ignored: already awaiting confirmation")
            return
        
        self.logger.info(f"AI Detection from '{model_name}': {len(detections)} object(s) detected")
        
        # Handle accident detection specifically
        if 'accident' in model_name.lower():
            self.logger.warning(f"Accident detected by AI model '{model_name}'!")
            self.awaiting_confirmation = True
            
            # Save snapshot of the detection frame
            snapshot_path = self._save_ai_detection_snapshot(frame)
            media = [snapshot_path] if snapshot_path else None
            
            # Report to central unit
            self.network.report_accident(lane_number="1", media=media, ai_detected=True)

    def _save_ai_detection_snapshot(self, frame) -> str:
        """
        Save a detection frame to disk.
        
        Args:
            frame: The frame to save (MatLike/numpy array)
            
        Returns:
            Path to saved image or None if failed
        """
        import cv2
        from datetime import datetime
        from utils.constants import ACCIDENT_IMAGES_DIR
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"ai_detection_{timestamp}.jpg"
            save_path = str(ACCIDENT_IMAGES_DIR / filename)
            
            ACCIDENT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
            if cv2.imwrite(save_path, frame):
                self.logger.info(f"Saved AI detection snapshot: {save_path}")
                return save_path
        except Exception as e:
            self.logger.error(f"Failed to save AI detection snapshot: {e}")
        return None

    def _on_central_unit_instruction(self, data: Dict[str, Any]):
        """Callback for incoming road state updates from Central Unit."""
        # Instruction received: reset the 'awaiting' flag
        if self.awaiting_confirmation:
            self.logger.info("Received instruction from Central Unit. Resolving AWAITING state.")
            self.awaiting_confirmation = False

        try:
            self.logger.info(f"Processing Central Unit Instruction: {data}")
            
            # 1. Check for Accident State
            is_accident = data.get('isAccident')
            
            if is_accident is False:
                self.logger.info("Central Unit dismissed/cleared alert. Resetting display.")
                self.io.reset_display()
                return

            if is_accident is True:
                self.io.toggle_alert(True)

            # 2. Update Speed Limit
            speed = data.get('speedLimit') or data.get('speed_limit')
            if speed is not None:
                self.io.update_speed(int(speed))

            # 3. Update Lane States
            lanes = data.get('laneStates') or data.get('lanes')
            if isinstance(lanes, list):
                for i, status in enumerate(lanes):
                    self.io.update_status(i, status)
                    
        except Exception as e:
            self.logger.error(f"Error processing central unit instruction: {e}")


if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    args = parse_args()
    node = SafespaceNode(
        video_path=args.video, 
        offline=args.offline,
        enable_ai=not args.no_ai
    )
    node.start()
