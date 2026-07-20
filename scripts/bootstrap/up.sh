#!/usr/bin/env bash
# Día cero DuckClaw — instala uv si falta y ejecuta duckops up.
# Wrapper raíz: ./duckops-up.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

log() { echo "🦆 $*"; }

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  log "Instalando uv (Astral)..."
  if command -v brew >/dev/null 2>&1; then
    if brew install uv; then
      command -v uv >/dev/null 2>&1 && return 0
    fi
  fi
  curl -LsSf https://astral.sh/uv/install.sh | sh
  if [[ -f "${HOME}/.local/bin/env" ]]; then
    # shellcheck source=/dev/null
    source "${HOME}/.local/bin/env"
  fi
  export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:${PATH}"
  command -v uv >/dev/null 2>&1
}

if ! ensure_uv; then
  echo "No se pudo instalar uv. Manual: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

log "duckops up …"
exec uv run duckops up "$@"
