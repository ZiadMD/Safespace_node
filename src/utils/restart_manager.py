"""
Restart Manager — clean process re-exec with a persisted restart marker.

Part of the CU-driven config-update flow: before restarting into a new
config, the caller writes a marker describing the restart (who initiated
it, which config version, where the pre-change config backup lives). On
the next boot, main.py checks for this marker very early so it can tell a
deliberate config-restart apart from a normal boot or a crash.

The restart itself is a re-exec (`os.execv`), not a process exit under a
supervisor: this repo has no systemd unit or wrapper script controlling
the process, so re-exec is the only way to guarantee the process comes
back at all. It also keeps the same PID and controlling terminal/stdio —
the terminal that launched the node stays open and attached.
"""
import json
import logging
import os
import sys
import time
import uuid
from typing import Any, Dict, Optional

from utils.constants import RESTART_MARKER_PATH


def write_marker(
    new_config_version: str,
    previous_config_backup_path: str,
    initiated_by: str,
    request_id: Optional[str] = None,
    attempt: int = 1,
    status: str = "pending",
    failure_reason: str = "",
) -> Dict[str, Any]:
    """
    Atomically persist the restart marker (temp file + os.rename) so a crash
    mid-write never leaves a half-written marker behind. Returns the marker.
    """
    marker = {
        "request_id": request_id or str(uuid.uuid4()),
        "new_config_version": new_config_version,
        "previous_config_backup_path": previous_config_backup_path,
        "initiated_by": initiated_by,
        "attempt": attempt,
        "status": status,
        "failure_reason": failure_reason,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
    }
    tmp_path = f"{RESTART_MARKER_PATH}.tmp"
    with open(tmp_path, "w") as f:
        json.dump(marker, f, indent=2)
    os.rename(tmp_path, RESTART_MARKER_PATH)
    return marker


def read_marker() -> Optional[Dict[str, Any]]:
    """Read the restart marker if present. Returns None if absent or unreadable."""
    if not RESTART_MARKER_PATH.exists():
        return None
    try:
        with open(RESTART_MARKER_PATH, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def clear_marker() -> None:
    """Delete the restart marker, if present."""
    try:
        RESTART_MARKER_PATH.unlink(missing_ok=True)
    except OSError:
        pass


def restart_process(logger=None) -> None:
    """
    Re-exec the current process in place: same PID, same controlling
    terminal/stdio, fresh Python interpreter and module state. Never
    returns — the process image is replaced.

    Caller is responsible for a clean shutdown (closing camera/serial/
    sockets/subprocesses) before calling this, since open file
    descriptors survive execv.
    """
    if logger:
        logger.info(f"Re-executing process: {sys.executable} {' '.join(sys.argv)}")
    logging.shutdown()
    os.execv(sys.executable, [sys.executable] + sys.argv)
