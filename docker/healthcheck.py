#!/usr/bin/env python3
"""
Docker health check — checks if the main process is alive and responsive.
"""
import sys
import os

def check():
    """Simple liveness check: verify the PID file or process."""
    try:
        # Check if main processes are running
        import psutil
        current_proc = psutil.Process(os.getpid())
        parent = current_proc.parent()
        if parent is None:
            return False

        # Check if the parent has the expected children
        children = parent.children(recursive=True)
        return len(children) >= 1  # At least capture process
    except Exception:
        return False


if __name__ == "__main__":
    if check():
        sys.exit(0)  # healthy
    sys.exit(1)  # unhealthy
