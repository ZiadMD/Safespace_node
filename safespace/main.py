import sys
import os
import signal
from typing import Dict, Any

from utils.config import Config
from utils.logger import Logger
from Managers.Network_Manager import NetworkManager
from Managers.IO_Manager import IOManager


class SafespaceNode:
    """
    Safespace Node Orchestrator.
    Manages the lifecycle and communication between Network and IO managers.
    """
    
    def __init__(self):
        # 1. Load Granular Configuration
        self.config = Config()
        
        # 2. Setup Global Logging
        Logger.setup(self.config.get('logging', {}))
        
        self.logger = Logger("SafespaceNode")
        self.logger.info("Initializing Safespace Node...")
        
        # 3. Initialize Managers
        self.network = NetworkManager(
            self.config, 
            on_central_unit_instruction=self._on_central_unit_instruction
        )
        
        self.io = IOManager(
            self.config, 
            on_manual_trigger=self._on_manual_accident_report
        )
        
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
        
        if not self.network.start():
            self.logger.warning("Network starting failed - Node running in offline mode")

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
    node = SafespaceNode()
    node.start()
