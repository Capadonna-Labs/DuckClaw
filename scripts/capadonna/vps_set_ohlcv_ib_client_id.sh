#!/usr/bin/env bash
# Añade OHLCV_IB_CLIENT_ID al servicio capadonna-observability (API :8002) para que
# ibkr_historical_bars.py no use el mismo clientId que otro proceso (Error 326).
#
# PREREQUISITO: en el VPS, scripts/capadonna/ibkr_historical_bars.py debe ser la versión
# de este repo (lee OHLCV_IB_CLIENT_ID). Una copia antigua solo usaba IB_CLIENT_ID→42 e
# ignoraba el drop-in. Ej.: scp scripts/capadonna/ibkr_historical_bars.py \
#   capadonna@HOST:/home/capadonna/projects/Capadonna-Driller/scripts/capadonna/
#
# ibkr_historical_bars.py lee: OHLCV_IB_CLIENT_ID → IB_CLIENT_ID → 42.
#
# Uso (desde una terminal interactiva con TTY, p. ej. Terminal.app / iTerm):
#   ./scripts/capadonna/vps_set_ohlcv_ib_client_id.sh
#
# Si ejecutas sin TTY (CI, algunos entornos) o sudo pide contraseña en el VPS:
#   ./scripts/capadonna/vps_set_ohlcv_ib_client_id.sh --print-remote
#   luego: ssh capadonna@TU_VPS  → pega el bloque en el servidor.
#
# Otro id:
#   OHLCV_IB_CLIENT_ID=47 SSH_TARGET=capadonna@100.97.151.69 ./scripts/capadonna/vps_set_ohlcv_ib_client_id.sh
#
set -euo pipefail
SSH_TARGET="${SSH_TARGET:-capadonna@100.97.151.69}"
CID="${OHLCV_IB_CLIENT_ID:-43}"

print_remote_block() {
  # Pegar esto en el VPS (sesión ssh interactiva) si el script remoto falla por sudo/TTY.
  cat <<EOF
# --- Copiar desde aquí (en el VPS, como usuario con sudo) ---
export CID=${CID}
DROPIN_DIR=/etc/systemd/system/capadonna-observability.service.d
DROPIN="\${DROPIN_DIR}/99-ohlcv-ib-client-id.conf"
UNIT=/etc/systemd/system/capadonna-observability.service
test -f "\$UNIT" || { echo "No existe \$UNIT"; exit 1; }
sudo mkdir -p "\$DROPIN_DIR"
printf '[Service]\\nEnvironment=OHLCV_IB_CLIENT_ID=%s\\n' "\$CID" | sudo tee "\$DROPIN" > /dev/null
sudo cat "\$DROPIN"
sudo systemctl daemon-reload
sudo systemctl restart capadonna-observability.service
systemctl is-active capadonna-observability.service
curl -sS -m 25 "http://127.0.0.1:8002/api/market/ohlcv?ticker=SPY&timeframe=1d&lookback_days=5" | head -c 400
echo
# --- Fin del bloque ---
EOF
}

if [[ "${1:-}" == "--print-remote" ]] || [[ "${1:-}" == "-n" ]]; then
  print_remote_block
  exit 0
fi

if [[ ! -t 0 ]] || [[ ! -t 1 ]]; then
  echo "Este script necesita una terminal interactiva (TTY) para que \"sudo\" en el VPS pueda pedir contraseña." >&2
  echo "Opciones:" >&2
  echo "  1) Abre Terminal.app / iTerm, cd al repo y vuelve a ejecutar: $0" >&2
  echo "  2) O imprime comandos para pegar tras \"ssh $SSH_TARGET\" y ejecuta allí:" >&2
  echo "" >&2
  print_remote_block
  exit 1
fi

# -tt fuerza PTY remoto aunque el cliente no tenga tty en algunos casos; sigue haciendo falta TTY local para sudo.
exec ssh -tt "$SSH_TARGET" "export CID='$CID'; bash -s" <<'REMOTE'
set -euo pipefail
DROPIN_DIR=/etc/systemd/system/capadonna-observability.service.d
DROPIN="${DROPIN_DIR}/99-ohlcv-ib-client-id.conf"
UNIT=/etc/systemd/system/capadonna-observability.service
if ! test -f "$UNIT"; then
  echo "No existe $UNIT — ajusta el nombre del servicio."
  exit 1
fi
sudo mkdir -p "$DROPIN_DIR"
echo "=== Escribiendo $DROPIN (OHLCV_IB_CLIENT_ID=$CID) ==="
printf '[Service]\nEnvironment=OHLCV_IB_CLIENT_ID=%s\n' "$CID" | sudo tee "$DROPIN" > /dev/null
sudo cat "$DROPIN"
sudo systemctl daemon-reload
sudo systemctl restart capadonna-observability.service
echo "=== Estado ==="
systemctl is-active capadonna-observability.service
echo "=== Environment (fragmento) ==="
systemctl show capadonna-observability.service -p Environment --no-pager | tr ' ' '\n' | grep -E 'OHLCV_IB|IB_CLIENT|IB_ENV' || true
echo "=== Prueba local (primeros 400 bytes) ==="
sleep 2
curl -sS -m 25 "http://127.0.0.1:8002/api/market/ohlcv?ticker=SPY&timeframe=1d&lookback_days=5" | head -c 400 || echo "(curl falló; journalctl -u capadonna-observability -n 40)"
echo
REMOTE
