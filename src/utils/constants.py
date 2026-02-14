"""
Global constants for the Safespace Node application.
"""
from pathlib import Path
import os

# Project Structure
BASE_DIR = Path(__file__).parent.parent          # → src/
PROJECT_ROOT = BASE_DIR.parent                   # → Safespace_node/
ASSETS_DIR = PROJECT_ROOT / "assets"
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
DEFAULT_SERVER_URL = "https://scarabaeoid-scrofulously-rupert.ngrok-free.dev"
CONNECTION_TIMEOUT = 10

# Lane Statuses
LANE_STATUS_UP = "up"
LANE_STATUS_BLOCKED = "blocked"
LANE_STATUS_LEFT = "left"
LANE_STATUS_RIGHT = "right"

# Socket.IO Events
EVENT_ACCIDENT_DETECTED = "node_accident_detected"  # Node → Server (Socket.IO)

# WebSocket Command IDs (Server → Node)
COMMAND_ACCIDENT_DECISION = "accident-decision"

# HTTP API Endpoints
API_NODE_REGISTER = "/api/nodes/register"
API_NODE_HEARTBEAT = "/api/nodes/heartbeat"

# Accident Decision Statuses
STATUS_CONFIRMED = "CONFIRMED"
STATUS_REJECTED = "REJECTED"

# Backend → Node lane-status mapping (backend uses "open", display uses "up")
BACKEND_LANE_STATUS_MAP = {
    "open": LANE_STATUS_UP,
    "blocked": LANE_STATUS_BLOCKED,
    "left": LANE_STATUS_LEFT,
    "right": LANE_STATUS_RIGHT,
}
