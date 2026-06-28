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
        connection.autoconnect yes
else
    echo "    profile absent — creating"
    sudo nmcli connection add type ethernet ifname "${IFACE}" con-name "${CON_NAME}" \
        ipv4.method manual \
        ipv4.addresses "${PI_IP}/${CIDR}" \
        ipv4.never-default yes \
        ipv6.method disabled \
        connection.autoconnect yes
fi

# (Re)activate so the address is live now.
sudo nmcli connection up "${CON_NAME}"

echo
echo "==> Applied address:"
ip -4 addr show "${IFACE}" | sed 's/^/    /'
echo
echo "==> Route to the Central Unit (must say 'dev ${IFACE}'):"
ip route get "${CU_IP}" | sed 's/^/    /'
echo
echo "Done. Verify reachability with:  ping -c3 ${CU_IP}"
