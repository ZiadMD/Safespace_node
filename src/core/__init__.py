"""
core — Shared infrastructure for Safespace Node v2.

Modules:
    config         — YAML config with dot-notation + env overrides
    logger         — Structured console + rotating file logging
    constants      — Paths, topics, statuses, display defaults
    message_bus    — Pub-sub over multiprocessing queues
    shared_memory  — Zero-copy frame slots across processes
    node_state     — Operating mode state machine (NORMAL/STREAMING/DEGRADED)
    supervisor     — Process health monitoring + mode transitions
"""
