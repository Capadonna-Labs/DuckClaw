#!/usr/bin/env bash
# Repara API IBKR (:8002) en VPS Hetzner: UFW + Tailscale Serve (fallback MagicDNS).
# SSH por IP pública si Tailscale IP no responde en puerto 22.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
eval "$(bash "${SCRIPT_DIR}/vps_ssh_resolve.sh")"

echo "==> UFW: puerto 8002 + tailscale0 en before.rules"
ssh -o BatchMode=yes "${SSH_TARGET}" bash -s <<'REMOTE'
set -euo pipefail
MARK="# tailscale-duckclaw"
BEFORE=/etc/ufw/before.rules
if ! grep -q "$MARK" "$BEFORE" 2>/dev/null; then
  sed -i "/^# End required lines/i\\
# ${MARK}\\
-A ufw-before-input -i tailscale0 -j ACCEPT\\
-A ufw-before-output -o tailscale0 -j ACCEPT\\
-A ufw-before-forward -i tailscale0 -j ACCEPT\\
-A ufw-before-forward -o tailscale0 -j ACCEPT\\
" "$BEFORE"
fi
ufw allow 8002/tcp comment "DuckClaw ibkr-ohlcv-api" 2>/dev/null || true
ufw allow in on tailscale0 to any port 8002 proto tcp 2>/dev/null || true
ufw reload
tailscale set --shields-up=false 2>/dev/null || true
REMOTE

echo "==> Tailscale Serve (HTTPS en tailnet si TCP directo a 100.x falla)"
ssh -o BatchMode=yes "${SSH_TARGET}" bash -s <<'REMOTE'
set -euo pipefail
if ! curl -sfS -m 2 http://127.0.0.1:8002/health >/dev/null; then
  echo "API local :8002 no responde; revisa capadonna-observability" >&2
  exit 1
fi
tailscale serve reset 2>/dev/null || true
tailscale serve --bg 8002
echo ""
tailscale serve status 2>&1 | head -8
DNS=$(tailscale status --json 2>/dev/null | python3 -c "import json,sys; print(json.load(sys.stdin).get('Self',{}).get('DNSName','').rstrip('.'))" 2>/dev/null || true)
echo ""
echo "MagicDNS (HTTPS, solo tailnet): https://${DNS}/"
REMOTE

echo ""
echo "=== Prueba desde tu Mac ==="
echo "  curl -sS http://100.75.4.17:8002/health"
echo "  curl -sS https://ubuntu-2gb-ash-1.tailc85db0.ts.net/health"
echo ""
echo "Si solo funciona la IP pública (87.99.156.231), actualiza .env temporalmente"
echo "o reinicia Tailscale en Mac: sudo tailscale down && sudo tailscale up"
