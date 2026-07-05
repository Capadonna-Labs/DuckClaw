#!/usr/bin/env bash
# Wrapper legacy → usa: uv run duckops stack deploy
#
#   cd <raíz-del-repo> && uv sync && uv run duckops stack deploy
#   uv run duckops stack deploy --no-migrate
#
# Remoto vía SSH (opcional):
#   bash scripts/deployment/deploy_macmini.sh --remote usuario@host
set -euo pipefail

REMOTE=""
MIGRATE_FLAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --remote)
      REMOTE="${2:-}"
      shift 2
      ;;
    --no-migrate)
      MIGRATE_FLAG="--no-migrate"
      shift
      ;;
    *)
      echo "Uso: $0 [--remote user@host] [--no-migrate]" >&2
      echo "Preferido: uv run duckops stack deploy [--no-migrate]" >&2
      exit 1
      ;;
  esac
done

deploy_body() {
  local ROOT
  ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
  cd "$ROOT"

  export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

  if [[ ! -f .env ]]; then
    echo "ERROR: falta .env en $ROOT" >&2
    exit 1
  fi

  if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv no está en PATH. Ejecuta: ./duckops-up.sh" >&2
    exit 1
  fi

  ARGS=()
  if [[ -n "$MIGRATE_FLAG" ]]; then
    ARGS+=("$MIGRATE_FLAG")
  fi

  echo "==> uv run duckops stack deploy …"
  exec uv run duckops stack deploy "${ARGS[@]}"
}

if [[ -n "$REMOTE" ]]; then
  echo "==> deploy remoto: $REMOTE"
  ssh -t "$REMOTE" "cd ~/Developer/duckclaw 2>/dev/null || cd ~/duckclaw; bash scripts/deployment/deploy_macmini.sh ${MIGRATE_FLAG}"
else
  deploy_body
fi
