"""Quick test script for the display package."""
import sys, threading, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from handlers.display import DisplayHandler
from utils.config import Config

config = Config()
display = DisplayHandler(config)

def simulate():
    time.sleep(2)
    print("→ Setting lane 1 BLOCKED, lane 2 RIGHT, speed 60, accident ON")
    display.update_lane_status(0, "blocked")
    display.update_lane_status(1, "right")
    display.update_speed_limit(60)
    display.set_accident_alert(True)
    time.sleep(5)
    print("→ Resetting display")
    display.reset_display()

threading.Thread(target=simulate, daemon=True).start()
display.start()
