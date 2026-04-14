#!/usr/bin/env bash
# Ajusta el servicio systemd capadonna-observability en el VPS para IB_ENV=paper
# (IB Gateway paper escucha en :4002; con IB_ENV=live la API intentaba :4001 → snapshot_unavailable).
#
# Uso (desde tu Mac, con acceso SSH al VPS):
#   chmod +x scripts/capadonna/vps_observability_ib_env_paper.sh
#   ./scripts/capadonna/vps_observability_ib_env_paper.sh
#
# O con otro host:
#   SSH_TARGET=capadonna@TU_HOST ./scripts/capadonna/vps_observability_ib_env_paper.sh
#
set -euo pipefail
SSH_TARGET="${SSH_TARGET:-capadonna@100.97.151.69}"

exec ssh -t "$SSH_TARGET" 'set -euo pipefail
UNIT=/etc/systemd/system/capadonna-observability.service
if ! test -f "$UNIT"; then
  echo "No existe $UNIT"; exit 1
fi
echo "=== Antes ==="
grep -E "^Environment=" "$UNIT" || true
sudo cp -a "$UNIT" "${UNIT}.bak.$(date +%Y%m%d%H%M%S)"
sudo sed -i '\''s/Environment="IB_ENV=live"/Environment="IB_ENV=paper"/'\'' "$UNIT" || sudo sed -i '\''s/IB_ENV=live/IB_ENV=paper/'\'' "$UNIT"
echo "=== Después ==="
grep -E "^Environment=" "$UNIT" || true
sudo systemctl daemon-reload
sudo systemctl restart capadonna-observability.service
echo "=== Estado ==="
systemctl is-active capadonna-observability.service
systemctl show capadonna-observability.service -p Environment,ActiveState,SubState --no-pager
echo "=== Prueba local /api/portfolio/summary (reintentos; uvicorn tarda ~1–3s en abrir :8002) ==="
_ok=0
for _i in 1 2 3 4 5 6 7 8 9 10; do
  if _out=$(curl -sfS -m 6 http://127.0.0.1:8002/api/portfolio/summary 2>/dev/null); then
    echo "$_out" | head -c 500
    echo
    _ok=1
    break
  fi
  echo "(intento $_i/10) aún no responde :8002, esperando 1s..."
  sleep 1
done
if [ "$_ok" != 1 ]; then
  echo "curl: no hubo respuesta en :8002. Revisa: journalctl -u capadonna-observability -n 50 --no-pager"
  exit 1
fi
'
