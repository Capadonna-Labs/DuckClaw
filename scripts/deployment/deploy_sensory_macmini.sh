#!/usr/bin/env bash
# Despliega sensory_node en Mac mini (Apple Silicon + Tailscale).
#
# En el Mac:
#   cd ~/duckclaw && bash scripts/deployment/deploy_sensory_macmini.sh
#
# Desde otra máquina con SSH:
#   bash scripts/deployment/deploy_sensory_macmini.sh --remote usuario@100.99.72.63
set -euo pipefail

REMOTE="${1:-}"
if [[ "${REMOTE}" == "--remote" ]]; then
  REMOTE="${2:-}"
fi

deploy_body() {
  local ROOT
  ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
  cd "$ROOT"

  export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

  if [[ ! -f .env ]]; then
    echo "ERROR: falta .env en $ROOT" >&2
    exit 1
  fi

  # No hacer `source .env` completo: valores con espacios (p. ej. CAPADONNA_REMOTE_OHLC_CMD) rompen bash.
  _read_env() {
    local key="$1"
    local default="${2:-}"
    local line
    line="$(grep -m1 "^${key}=" .env 2>/dev/null || true)"
    if [[ -z "$line" ]]; then
      printf '%s' "$default"
      return
    fi
    printf '%s' "${line#${key}=}"
  }
  export DUCKCLAW_SENSORY_BIND_HOST="$(_read_env DUCKCLAW_SENSORY_BIND_HOST)"
  export DUCKCLAW_SENSORY_PORT="$(_read_env DUCKCLAW_SENSORY_PORT 8001)"

  if [[ -z "${DUCKCLAW_SENSORY_BIND_HOST:-}" ]]; then
    echo "ERROR: define DUCKCLAW_SENSORY_BIND_HOST (IP Tailscale del Mac)" >&2
    exit 1
  fi

  echo "==> uv sync sensory-node"
  uv sync --project integrations/sensory-node

  chmod +x integrations/sensory-node/scripts/start_sensory.sh

  if pm2 describe Sensory-Node >/dev/null 2>&1; then
    echo "==> pm2 restart Sensory-Node"
    pm2 restart Sensory-Node --update-env
  else
    echo "==> pm2 start Sensory-Node"
    pm2 start config/ecosystem.sensory.config.cjs
  fi
  pm2 save 2>/dev/null || true

  PORT="${DUCKCLAW_SENSORY_PORT:-8001}"
  echo "==> health http://${DUCKCLAW_SENSORY_BIND_HOST}:${PORT}/health"
  curl -sf --max-time 15 "http://${DUCKCLAW_SENSORY_BIND_HOST}:${PORT}/health"
  echo ""
  echo "OK: Sensory-Node listo"
}

if [[ -n "${REMOTE}" ]]; then
  echo "==> deploy remoto: $REMOTE"
  ssh -o ConnectTimeout=20 "$REMOTE" 'bash -s' <<'REMOTE_SCRIPT'
set -euo pipefail
for ROOT in "$HOME/duckclaw" "$HOME/Desktop/duckclaw"; do
  if [[ -d "$ROOT/.git" ]]; then
    cd "$ROOT"
    git pull --ff-only 2>/dev/null || true
    exec bash scripts/deployment/deploy_sensory_macmini.sh
  fi
done
echo "ERROR: no se encontró duckclaw en ~/duckclaw ni ~/Desktop/duckclaw" >&2
exit 1
REMOTE_SCRIPT
else
  deploy_body
fi
