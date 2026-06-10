#!/usr/bin/env bash
# Aplica el parche TTS en el Mac mini (ejecutar EN el Mac con repo duckclaw).
set -eu
set -o pipefail 2>/dev/null || true

PATCH="${1:-/tmp/tts-sensory-patch.tar.gz}"
for ROOT in "$HOME/duckclaw" "$HOME/Desktop/duckclaw"; do
  if [[ -d "$ROOT/.git" ]]; then
    cd "$ROOT"
    echo "==> extract patch into $ROOT"
    tar -xzf "$PATCH" -C "$ROOT"
    if [[ -f scripts/deployment/patch_tts_production_env.py ]]; then
      python3 scripts/deployment/patch_tts_production_env.py --mac-env "$ROOT/.env"
    fi
    chmod +x integrations/sensory-node/scripts/start_sensory.sh
    if pm2 describe Sensory-Node >/dev/null 2>&1; then
      pm2 restart Sensory-Node --update-env
    else
      pm2 start config/ecosystem.sensory.config.cjs
    fi
    echo "==> health"
    BIND="$(grep -m1 '^DUCKCLAW_SENSORY_BIND_HOST=' .env | cut -d= -f2-)"
    PORT="$(grep -m1 '^DUCKCLAW_SENSORY_PORT=' .env | cut -d= -f2-)"
    PORT="${PORT:-8001}"
    curl -sf --max-time 15 "http://${BIND}:${PORT}/health" || true
    echo ""
    echo "OK: TTS patch aplicado. Opcional: bash scripts/deployment/regen_voices_mac.py"
    exit 0
  fi
done
echo "ERROR: no se encontró duckclaw en ~/duckclaw ni ~/Desktop/duckclaw" >&2
exit 1
