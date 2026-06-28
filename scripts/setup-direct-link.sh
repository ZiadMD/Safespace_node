#!/usr/bin/env bash
#
# setup-direct-link.sh — pin the Pi's wired interface to a static IP for the
# direct Ethernet link to the Central Unit (CU).
#
# A direct cable has no DHCP, so addressing must be deterministic. This creates
# (or updates) a dedicated NetworkManager profile that gives eth0 a fixed IP on
# a private /24 WITHOUT becoming the default route — so internet over Wi-Fi keeps
# working. Idempotent: safe to re-run.
#
# It sets a high autoconnect-priority so this profile wins the interface over any
# pre-existing default profile (e.g. NetworkManager's auto-created
# "Wired connection 1") without deleting it. If there is no carrier yet (cable
# unplugged / no link) the profile is staged and auto-activates once a link appears.
#
# Target stack: NetworkManager (Raspberry Pi OS Bookworm and later).
#
# Usage:
#   sudo ./scripts/setup-direct-link.sh
#   sudo PI_IP=192.168.50.10 CU_IP=192.168.50.1 IFACE=eth0 ./scripts/setup-direct-link.sh
#
# Override any of these via the environment:
set -euo pipefail

IFACE="${IFACE:-eth0}"               # wired interface on the Pi
PI_IP="${PI_IP:-192.168.50.10}"      # this Pi's static address on the link
CIDR="${CIDR:-24}"                   # prefix length (/24 private link)
CU_IP="${CU_IP:-192.168.50.1}"       # Central Unit address (for verification only)
CON_NAME="${CON_NAME:-direct-link}"  # NetworkManager profile name

if ! command -v nmcli >/dev/null 2>&1; then
    echo "error: nmcli not found — this script targets NetworkManager." >&2
    echo "       Detect your stack with:  ls -l /etc/systemd/system/dbus-org.freedesktop.network1.service 2>/dev/null; systemctl is-active NetworkManager dhcpcd systemd-networkd" >&2
    exit 1
fi

echo "==> Configuring '${CON_NAME}' on ${IFACE}: ${PI_IP}/${CIDR} (CU ${CU_IP}, no default route)"

# Create the profile if absent, otherwise update it in place (idempotent).
if nmcli -t -f NAME connection show | grep -qx "${CON_NAME}"; then
    echo "    profile exists — updating"
    sudo nmcli connection modify "${CON_NAME}" \
        connection.interface-name "${IFACE}" \
        ipv4.method manual \
        ipv4.addresses "${PI_IP}/${CIDR}" \
        ipv4.gateway "" \
        ipv4.never-default yes \
        ipv6.method disabled \
        connection.autoconnect yes \
        connection.autoconnect-priority 10
else
    echo "    profile absent — creating"
    sudo nmcli connection add type ethernet ifname "${IFACE}" con-name "${CON_NAME}" \
        ipv4.method manual \
        ipv4.addresses "${PI_IP}/${CIDR}" \
        ipv4.never-default yes \
        ipv6.method disabled \
        connection.autoconnect yes \
        connection.autoconnect-priority 10
fi

# (Re)activate so the address is live now. Tolerate "no carrier" — the profile is
# staged either way and NetworkManager brings it up automatically once a link exists.
echo "==> Activating ${CON_NAME}..."
if sudo nmcli connection up "${CON_NAME}" 2>/dev/null; then
    echo "    active"
else
    echo "    not active yet — most likely NO CARRIER (cable unplugged or no link)."
    echo "    Check the physical link:  sudo ethtool ${IFACE} | grep -i 'link detected'"
    echo "    The profile is staged; it auto-activates when a live link appears."
fi

echo
echo "==> Profile (staged config):"
nmcli -f connection.id,ipv4.method,ipv4.addresses,ipv4.never-default,connection.autoconnect-priority \
    connection show "${CON_NAME}" 2>/dev/null | sed 's/^/    /' || true
echo
echo "==> Live address on ${IFACE}:"
ip -4 addr show "${IFACE}" 2>/dev/null | sed 's/^/    /' || true
echo
echo "==> Route to the Central Unit (should say 'dev ${IFACE}' once the link is up):"
ip route get "${CU_IP}" 2>/dev/null | sed 's/^/    /' || echo "    (no route yet — link down or CU side not configured)"
echo
echo "Done. When the cable is live, verify with:  ping -c3 ${CU_IP}"
