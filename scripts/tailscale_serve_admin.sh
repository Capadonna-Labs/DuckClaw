#!/usr/bin/env bash
# Expone la consola admin (Next.js) en la tailnet vía Tailscale Serve (HTTPS :8443).
# No toca el Funnel del gateway (:443 → :8000). Requiere Tailscale conectado.
#
# Uso:
#   pnpm admin:dev                    # en otra terminal (anota el puerto, ej. 3000 o 3001)
#   DUCKCLAW_ADMIN_PORT=3001 ./scripts/tailscale_serve_admin.sh
#
# URL en el celular (app Tailscale activa):
#   https://<tu-maquina>.<tailnet>.ts.net:8443/

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${DUCKCLAW_ADMIN_PORT:-3001}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "tailscale CLI no encontrado. Instala Tailscale en este Mac." >&2
  exit 1
fi

if ! tailscale status >/dev/null 2>&1; then
  echo "Tailscale no está conectado. Abre la app y conecta la tailnet." >&2
  exit 1
fi

echo "Sirviendo admin en tailnet: https://…:8443/ → http://127.0.0.1:${PORT}/"
tailscale serve --bg --https=8443 "http://127.0.0.1:${PORT}"

DNS="$(tailscale status --json 2>/dev/null | python3 -c "
import json, sys
d = json.load(sys.stdin)
print(d.get('Self', {}).get('DNSName', '').rstrip('.'))
" 2>/dev/null || true)"

if [[ -n "${DNS}" ]]; then
  echo ""
  echo "Abre en el celular (con Tailscale):"
  echo "  https://${DNS}:8443/"
else
  IP="$(tailscale ip -4 2>/dev/null | head -1 || true)"
  echo ""
  echo "Abre en el celular (con Tailscale):"
  echo "  https://${IP:-<tailscale-ip>}:8443/"
fi

echo ""
echo "Gateway (Funnel/Telegram) sigue en :443 → 127.0.0.1:8000 (sin cambios)."
echo "Para quitar: tailscale serve --https=8443 off"
