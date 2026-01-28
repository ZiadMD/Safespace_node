"""
Global constants for the Safespace Node application.
"""
from pathlib import Path

# Project Structure
BASE_DIR = Path(__file__).parent.parent
ASSETS_DIR = BASE_DIR / "assets"
LOGS_DIR = BASE_DIR / "logs"

# Asset Paths
ROAD_SIGNS_DIR = ASSETS_DIR / "road_signs_icons"
ACCIDENT_IMAGES_DIR = ASSETS_DIR / "accidents_images"
DEFAULT_ACCIDENT_IMAGE = ACCIDENT_IMAGES_DIR / "accident.png"

# Display Settings
DEFAULT_WINDOW_WIDTH = 1500
DEFAULT_WINDOW_HEIGHT = 856
ASPECT_RATIO = 16 / 9
MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 540

# Network Settings
DEFAULT_HEARTBEAT_INTERVAL = 30
DEFAULT_SERVER_URL = "http://localhost:5000"
CONNECTION_TIMEOUT = 10

# Lane Statuses
LANE_STATUS_UP = "up"
LANE_STATUS_BLOCKED = "blocked"
LANE_STATUS_LEFT = "left"
LANE_STATUS_RIGHT = "right"

# Socket.io Events
EVENT_ROAD_UPDATE = "road_update"
EVENT_CENTRAL_UNIT_UPDATE = "central_unit_update"
EVENT_HEARTBEAT = "heartbeat"
EVENT_ACCIDENT_REPORT = "/api/accident-detected"
