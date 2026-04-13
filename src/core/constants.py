"""
Global constants for Safespace Node v2.
"""
from pathlib import Path

# ── Project Structure ─────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent          # → src/
PROJECT_ROOT = BASE_DIR.parent                   # → Safespace_node/
ASSETS_DIR = PROJECT_ROOT / "assets"
LOGS_DIR = BASE_DIR / "logs"
ROAD_SIGNS_DIR = ASSETS_DIR / "road_signs_icons"

# ── Display Defaults ──────────────────────────────────────────
DEFAULT_WINDOW_WIDTH = 1500
DEFAULT_WINDOW_HEIGHT = 856
MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 540

# ── Network / API ─────────────────────────────────────────────
API_NODE_REGISTER = "/api/nodes/register"
API_NODE_HEARTBEAT = "/api/nodes/heartbeat"

# Socket.IO events
EVENT_ACCIDENT_DETECTED = "node_accident_detected"

# WebSocket command IDs (server → node)
COMMAND_ACCIDENT_DECISION = "accident-decision"
COMMAND_START_STREAM = "start-stream"
COMMAND_STOP_STREAM = "stop-stream"

# Accident decision statuses
STATUS_CONFIRMED = "CONFIRMED"
STATUS_REJECTED = "REJECTED"

# Lane statuses
LANE_STATUS_UP = "up"
LANE_STATUS_BLOCKED = "blocked"
LANE_STATUS_LEFT = "left"
LANE_STATUS_RIGHT = "right"

# Backend → display lane mapping
BACKEND_LANE_STATUS_MAP = {
    "open": LANE_STATUS_UP,
    "blocked": LANE_STATUS_BLOCKED,
    "left": LANE_STATUS_LEFT,
    "right": LANE_STATUS_RIGHT,
}

# ── Message Bus Topics ────────────────────────────────────────
TOPIC_FRAME_CAPTURED = "frame.captured"
TOPIC_FRAME_ANNOTATED = "frame.annotated"
TOPIC_DETECTION = "detection.accident"
TOPIC_AI_HEALTH = "ai.health_ping"
TOPIC_MODE_CHANGED = "mode.changed"
TOPIC_ROAD_UPDATE = "command.road_update"
TOPIC_ACCIDENT_DECISION = "command.accident_decision"
TOPIC_SHUTDOWN = "system.shutdown"

# ── Display Theme Colors ─────────────────────────────────────
THEME_BG = "#1a1a2e"
THEME_ACCENT = "#00d4ff"
THEME_SUCCESS = "#00ff88"
THEME_DANGER = "#ff4444"
THEME_WARNING = "#ffa500"
THEME_TEXT = "#ffffff"
THEME_MUTED = "#888888"
THEME_DIM = "#555555"
