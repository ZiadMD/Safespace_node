"""
Config Manager — CU-driven configuration updates over a dedicated WebSocket.

Owns the config channel (handlers/config_channel.py) and the full lifecycle
of a CU-pushed config change:

    config.update (valid)  -> backup + atomic persist -> write restart marker
        -> caller (SafespaceNode) restarts the process cleanly (re-exec)
    boot after restart     -> SafespaceNode runs a health gate, then calls
        report_health():
            success              -> clear marker, send config.applied(success)
            failure, attempts left -> restore backup, rewrite marker
                                     (status=rolling_back, attempt+1), restart again
            failure, attempts exhausted -> stay on last-known-good config,
                                     send one config.applied(rolledback) with reason
            success on a rolling_back boot -> send config.applied(rolledback):
                                     the rollback itself succeeded, but the
                                     CU's pushed config was never applied

config.update (invalid) -> config.ack(rejected) with a reason. Nothing is
persisted and nothing restarts.

config.applied notifications are persisted to disk and retried on the next
channel reconnect if the CU is unreachable when they need to be sent —
unlike accident reports (handlers/socket.py), which are dropped silently
when the socket is offline.
"""
import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import yaml

from utils.config import Config
from utils.constants import CONFIG_NOTIFY_QUEUE_PATH
from utils.logger import Logger
from utils import restart_manager
from handlers.config_channel import ConfigChannelHandler


# Camera modes CameraHandler actually supports — see CLAUDE.md's
# "IMX500 camera modes" table.
VALID_CAMERA_MODES = {"picam", "imx500", "imx500-raw"}
VALID_DISPLAY_MODES = {"dev", "prod"}
VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# Loop guard: total restart attempts (initial push + rollback) before giving
# up and staying on the last-known-good config.
MAX_RESTART_ATTEMPTS = 2


class ConfigManager:
    """
    Usage (from main.py):
        config_manager = ConfigManager(config, on_restart_requested=self._restart_for_config)
        config_manager.start()
        ...
        if config_manager.has_pending_marker:
            healthy, reason = self._run_health_gate()
            config_manager.report_health(healthy, reason)
        ...
        config_manager.stop()
    """

    def __init__(self, config: Config, on_restart_requested: Optional[Callable[[], None]] = None):
        self.logger = Logger("ConfigManager")
        self.config = config
        self._on_restart_requested = on_restart_requested

        self._channel = ConfigChannelHandler(
            config,
            on_message=self._on_message,
            on_connect=self._on_channel_connect,
        )

        # Marker left behind by a CU-driven restart. A marker not initiated
        # by "cu" (e.g. the Phase-1 debug self-test) isn't ours to manage.
        marker = restart_manager.read_marker()
        self._marker: Optional[Dict[str, Any]] = marker if marker and marker.get("initiated_by") == "cu" else None
        self._health_reported = False

    # ══════════════════════════════════════════════════════════════
    # Lifecycle
    # ══════════════════════════════════════════════════════════════

    def start(self):
        self.logger.info("Starting Config Manager...")
        self._channel.connect()

    def stop(self):
        self._channel.disconnect()
        self.logger.info("Config Manager stopped")

    @property
    def has_pending_marker(self) -> bool:
        return self._marker is not None

    # ══════════════════════════════════════════════════════════════
    # Inbound message dispatch
    # ══════════════════════════════════════════════════════════════

    def _on_message(self, message: Dict[str, Any]):
        msg_type = message.get("type")
        if msg_type == "config.update":
            self._handle_config_update(message)
        else:
            self.logger.warning(f"Unknown config channel message type: {msg_type}")

    def _on_channel_connect(self):
        """Flush any config.applied notifications queued while offline."""
        self._flush_notify_queue()

    # ══════════════════════════════════════════════════════════════
    # config.update — validate, ack, persist, restart
    # ══════════════════════════════════════════════════════════════

    def _handle_config_update(self, message: Dict[str, Any]):
        request_id = message.get("request_id")
        config_version = message.get("config_version")
        new_config = message.get("config")

        valid, reason = self._validate_config(new_config)
        if not valid:
            self.logger.warning(f"Rejected config update {request_id}: {reason}")
            self._channel.send({
                "type": "config.ack",
                "request_id": request_id,
                "status": "rejected",
                "reason": reason,
            })
            return

        try:
            backup_path = self._backup_current_config()
            self._atomic_write_config(new_config)
        except Exception as e:
            self.logger.error(f"Failed to persist config update {request_id}: {e}")
            self._channel.send({
                "type": "config.ack",
                "request_id": request_id,
                "status": "rejected",
                "reason": f"persist failed: {e}",
            })
            return

        self.logger.info(f"Config update {request_id} accepted — persisted (backup={backup_path})")
        self._channel.send({
            "type": "config.ack",
            "request_id": request_id,
            "status": "accepted",
        })

        restart_manager.write_marker(
            new_config_version=config_version or self._hash_config(new_config),
            previous_config_backup_path=backup_path,
            initiated_by="cu",
            request_id=request_id,
            attempt=1,
            status="pending",
        )

        if self._on_restart_requested:
            self._on_restart_requested()

    def _validate_config(self, new_config: Any) -> Tuple[bool, Optional[str]]:
        """
        Validate a CU-pushed config before it ever touches disk: key
        presence/types/ranges, and camera.model restricted to the three
        modes CameraHandler actually supports.
        """
        if not isinstance(new_config, dict):
            return False, "config must be a JSON object"

        def get(path: str, default=None):
            cur: Any = new_config
            for part in path.split('.'):
                if not isinstance(cur, dict) or part not in cur:
                    return default
                cur = cur[part]
            return cur

        camera_model = get("camera.model")
        if camera_model is not None and camera_model not in VALID_CAMERA_MODES:
            return False, f"camera.model must be one of {sorted(VALID_CAMERA_MODES)}, got {camera_model!r}"

        lanes = get("node.lanes")
        if lanes is not None and (not isinstance(lanes, int) or isinstance(lanes, bool) or lanes <= 0):
            return False, "node.lanes must be a positive integer"

        default_speed = get("node.default_speed")
        if default_speed is not None and (not isinstance(default_speed, (int, float)) or isinstance(default_speed, bool) or default_speed <= 0):
            return False, "node.default_speed must be a positive number"

        width = get("camera.resolution.width")
        if width is not None and (not isinstance(width, int) or isinstance(width, bool) or width <= 0):
            return False, "camera.resolution.width must be a positive integer"

        height = get("camera.resolution.height")
        if height is not None and (not isinstance(height, int) or isinstance(height, bool) or height <= 0):
            return False, "camera.resolution.height must be a positive integer"

        fps = get("camera.fps")
        if fps is not None and (not isinstance(fps, (int, float)) or isinstance(fps, bool) or fps <= 0):
            return False, "camera.fps must be a positive number"

        ai_models = get("ai.models")
        if ai_models is not None:
            if not isinstance(ai_models, dict):
                return False, "ai.models must be an object"
            for name, model_cfg in ai_models.items():
                if not isinstance(model_cfg, dict):
                    return False, f"ai.models.{name} must be an object"
                conf = model_cfg.get("confidence")
                if conf is not None and (not isinstance(conf, (int, float)) or isinstance(conf, bool) or not (0 <= conf <= 1)):
                    return False, f"ai.models.{name}.confidence must be between 0 and 1"
                enabled = model_cfg.get("enabled")
                if enabled is not None and not isinstance(enabled, bool):
                    return False, f"ai.models.{name}.enabled must be a boolean"

        stream_port = get("stream.port")
        if stream_port is not None and (not isinstance(stream_port, int) or isinstance(stream_port, bool) or not (1 <= stream_port <= 65535)):
            return False, "stream.port must be an integer between 1 and 65535"

        server_url = get("network.server_url")
        if server_url is not None:
            if not isinstance(server_url, str) or not (server_url.startswith("http://") or server_url.startswith("https://")):
                return False, "network.server_url must be an http(s) URL"

        heartbeat_interval = get("network.heartbeat_interval")
        if heartbeat_interval is not None and (not isinstance(heartbeat_interval, (int, float)) or isinstance(heartbeat_interval, bool) or heartbeat_interval <= 0):
            return False, "network.heartbeat_interval must be a positive number"

        accident_cooldown = get("network.accident_cooldown")
        if accident_cooldown is not None and (not isinstance(accident_cooldown, (int, float)) or isinstance(accident_cooldown, bool) or accident_cooldown < 0):
            return False, "network.accident_cooldown must be a non-negative number"

        baud_rate = get("gps.baud_rate")
        if baud_rate is not None and (not isinstance(baud_rate, int) or isinstance(baud_rate, bool) or baud_rate <= 0):
            return False, "gps.baud_rate must be a positive integer"

        display_mode = get("display.mode")
        if display_mode is not None and display_mode not in VALID_DISPLAY_MODES:
            return False, f"display.mode must be one of {sorted(VALID_DISPLAY_MODES)}"

        log_level = get("logging.level")
        if log_level is not None and str(log_level).upper() not in VALID_LOG_LEVELS:
            return False, f"logging.level must be one of {sorted(VALID_LOG_LEVELS)}"

        return True, None

    @staticmethod
    def _hash_config(new_config: dict) -> str:
        canonical = json.dumps(new_config, sort_keys=True).encode("utf-8")
        return hashlib.sha256(canonical).hexdigest()[:12]

    def _config_file_path(self) -> Path:
        return Path(self.config.config_file_path)

    def _backup_current_config(self) -> str:
        src = self._config_file_path()
        dst = Path(str(src) + ".bak")
        shutil.copy2(src, dst)
        return str(dst)

    def _atomic_write_config(self, new_config: dict):
        dst = self._config_file_path()
        tmp = Path(str(dst) + ".tmp")
        with open(tmp, "w") as f:
            yaml.dump(new_config, f, default_flow_style=False, sort_keys=False)
        os.rename(tmp, dst)

    # ══════════════════════════════════════════════════════════════
    # Health gate result — called once by SafespaceNode after boot
    # ══════════════════════════════════════════════════════════════

    def report_health(self, healthy: bool, reason: str = ""):
        """No-op on a normal boot (no pending marker)."""
        if not self._marker:
            return
        self._health_reported = True
        marker = self._marker
        is_rollback_boot = marker.get("status") == "rolling_back"

        if healthy:
            if is_rollback_boot:
                # Back on the last-known-good config after a failed push —
                # the rollback succeeded, but the CU's config never applied.
                original_reason = marker.get("failure_reason") or reason or "health gate failed after config update"
                self.logger.info(
                    f"Rollback succeeded — config v{marker.get('new_config_version')} was not applied "
                    f"({original_reason})"
                )
                self._notify_applied(marker, status="rolledback", reason=original_reason)
                self._cleanup_marker_and_backup(marker)
            else:
                self.logger.info(
                    f"Health gate passed — config v{marker.get('new_config_version')} applied successfully"
                )
                self._notify_applied(marker, status="success")
                self._cleanup_marker_and_backup(marker)
            return

        attempt = int(marker.get("attempt", 1))
        self.logger.error(f"Health gate failed (attempt {attempt}/{MAX_RESTART_ATTEMPTS}): {reason}")

        if attempt >= MAX_RESTART_ATTEMPTS:
            self.logger.error(
                "Restart attempts exhausted — staying on last-known-good config, "
                "notifying hard failure"
            )
            self._notify_applied(marker, status="rolledback", reason=f"attempts exhausted: {reason}")
            self._cleanup_marker_and_backup(marker)
            return

        self._rollback_to_backup(marker)
        restart_manager.write_marker(
            new_config_version=marker.get("new_config_version"),
            previous_config_backup_path=marker.get("previous_config_backup_path", ""),
            initiated_by="cu",
            request_id=marker.get("request_id"),
            attempt=attempt + 1,
            status="rolling_back",
            failure_reason=reason,
        )
        if self._on_restart_requested:
            self._on_restart_requested()

    def _rollback_to_backup(self, marker: Dict[str, Any]):
        backup_path = marker.get("previous_config_backup_path")
        if not backup_path or not os.path.exists(backup_path):
            self.logger.error(f"Cannot roll back — backup missing: {backup_path}")
            return
        dst = self._config_file_path()
        shutil.copy2(backup_path, dst)
        self.logger.info(f"Rolled back config from backup: {backup_path}")

    def _cleanup_marker_and_backup(self, marker: Dict[str, Any]):
        restart_manager.clear_marker()
        backup_path = marker.get("previous_config_backup_path")
        if backup_path and os.path.exists(backup_path):
            try:
                os.remove(backup_path)
            except OSError:
                pass

    # ══════════════════════════════════════════════════════════════
    # config.applied — persisted + retried if the CU is unreachable
    # ══════════════════════════════════════════════════════════════

    def _notify_applied(self, marker: Dict[str, Any], status: str, reason: str = ""):
        notification = {
            "type": "config.applied",
            "request_id": marker.get("request_id"),
            "config_version": marker.get("new_config_version"),
            "status": status,
        }
        if reason:
            notification["reason"] = reason

        if self._channel.is_connected and self._channel.send(notification):
            self.logger.info(f"Sent config.applied ({status}) for {notification['request_id']}")
            return

        self.logger.warning(
            f"Config channel offline — queuing config.applied ({status}) for retry on reconnect"
        )
        self._queue_notification(notification)

    def _queue_notification(self, notification: Dict[str, Any]):
        queue = self._read_notify_queue()
        queue.append(notification)
        self._write_notify_queue(queue)

    def _flush_notify_queue(self):
        queue = self._read_notify_queue()
        if not queue:
            return
        remaining = []
        for notification in queue:
            if self._channel.send(notification):
                self.logger.info(
                    f"Delivered queued config.applied ({notification.get('status')}) "
                    f"for {notification.get('request_id')}"
                )
            else:
                remaining.append(notification)
        self._write_notify_queue(remaining)

    @staticmethod
    def _read_notify_queue() -> List[Dict[str, Any]]:
        if not CONFIG_NOTIFY_QUEUE_PATH.exists():
            return []
        try:
            with open(CONFIG_NOTIFY_QUEUE_PATH, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    @staticmethod
    def _write_notify_queue(queue: List[Dict[str, Any]]):
        if not queue:
            try:
                CONFIG_NOTIFY_QUEUE_PATH.unlink(missing_ok=True)
            except OSError:
                pass
            return
        tmp_path = f"{CONFIG_NOTIFY_QUEUE_PATH}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(queue, f, indent=2)
        os.rename(tmp_path, CONFIG_NOTIFY_QUEUE_PATH)
