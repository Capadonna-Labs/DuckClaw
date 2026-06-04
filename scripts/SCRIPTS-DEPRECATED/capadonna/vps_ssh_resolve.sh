#!/usr/bin/env bash
# Resuelve SSH al VPS Hetzner: Tailscale (100.75.4.17) suele fallar; IP pública (87.99.156.231) funciona.
# Fuente: export $(bash scripts/SCRIPTS-DEPRECATED/capadonna/vps_ssh_resolve.sh)
set -euo pipefail

TS_HOST="${VPS_TAILSCALE_IP:-100.75.4.17}"
PUB_HOST="${VPS_PUBLIC_IP:-87.99.156.231}"
SSH_USER="${VPS_SSH_USER:-root}"
TS_TARGET="${SSH_USER}@${TS_HOST}"
PUB_TARGET="${SSH_USER}@${PUB_HOST}"

_ssh_ok() {
  ssh -o BatchMode=yes -o ConnectTimeout=8 "$1" "echo ok" >/dev/null 2>&1
}

if _ssh_ok "${TS_TARGET}"; then
  echo "SSH_TARGET=${TS_TARGET}"
  echo "SSH_VIA=tailscale"
elif _ssh_ok "${PUB_TARGET}"; then
  echo "SSH_TARGET=${PUB_TARGET}"
  echo "SSH_VIA=public"
else
  echo "SSH_TARGET=${TS_TARGET}" >&2
  echo "SSH_VIA=none" >&2
  echo "No hay SSH por ${TS_HOST} ni ${PUB_HOST}. ¿Tailscale activo? ¿Puerto 22 abierto?" >&2
  exit 1
fi
