#!/bin/bash
# Safespace Node — Docker entrypoint
# Applies any last-minute env var configuration before starting

echo "=== Safespace Node v2 ==="
echo "Device:  ${SAFESPACE_DEVICE:-unknown}"
echo "Node ID: ${NODE_ID:-from-config}"
echo "Server:  ${SERVER_URL:-from-config}"
echo "========================="

exec "$@"
