#!/usr/bin/env bash
# Arranca ComfyUI (API HTTP) para DuckClaw. Usado por PM2 (ComfyUI).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if command -v git >/dev/null 2>&1; then
  _GIT_ROOT="$(git -C "${REPO_ROOT}" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "${_GIT_ROOT}" ] && [ -f "${_GIT_ROOT}/.env" ]; then
    REPO_ROOT="${_GIT_ROOT}"
  fi
fi

if [ -f "${REPO_ROOT}/.env" ]; then
  set -a
  # shellcheck source=/dev/null
  source "${REPO_ROOT}/.env"
  set +a
fi

COMFY_HOME="${COMFYUI_HOME:-${HOME}/ComfyUI}"
if [ ! -d "${COMFY_HOME}" ]; then
  echo "ERROR: COMFYUI_HOME no existe: ${COMFY_HOME}" >&2
  echo "Define COMFYUI_HOME en .env (ej. COMFYUI_HOME=${HOME}/ComfyUI)" >&2
  exit 1
fi

API_URL="${COMFYUI_API_URL:-http://127.0.0.1:8188}"
LISTEN_HOST="127.0.0.1"
PORT="8188"
if [[ "${API_URL}" =~ ^https?://([^:/]+)(:([0-9]+))? ]]; then
  LISTEN_HOST="${BASH_REMATCH[1]}"
  if [ -n "${BASH_REMATCH[3]:-}" ]; then
    PORT="${BASH_REMATCH[3]}"
  fi
fi

PYTHON=""
for candidate in \
  "${COMFYUI_PYTHON:-}" \
  "${COMFY_HOME}/venv/bin/python" \
  "${COMFY_HOME}/.venv/bin/python"; do
  if [ -n "${candidate}" ] && [ -x "${candidate}" ]; then
    PYTHON="${candidate}"
    break
  fi
done
if [ -z "${PYTHON}" ]; then
  PYTHON="$(command -v python3 || command -v python || true)"
fi
if [ -z "${PYTHON}" ]; then
  echo "ERROR: no se encontró python para ComfyUI en ${COMFY_HOME}" >&2
  exit 1
fi

if [ ! -f "${COMFY_HOME}/main.py" ]; then
  echo "ERROR: falta ${COMFY_HOME}/main.py (¿instalación ComfyUI incompleta?)" >&2
  exit 1
fi

HEALTH_URL="${API_URL%/}/system_stats"
if command -v curl >/dev/null 2>&1 && curl -sf --max-time 3 "${HEALTH_URL}" >/dev/null 2>&1; then
  echo "ComfyUI ya responde en ${API_URL} — no se inicia otra instancia."
  exit 0
fi

if command -v lsof >/dev/null 2>&1; then
  PORT_PID="$(lsof -tiTCP:"${PORT}" -sTCP:LISTEN 2>/dev/null | head -1 || true)"
  if [ -n "${PORT_PID}" ]; then
    echo "ERROR: puerto ${PORT} ocupado por PID ${PORT_PID} (no responde ${HEALTH_URL})." >&2
    echo "Cierra el proceso huérfano: kill ${PORT_PID}  o  pm2 delete ComfyUI && reinicia." >&2
    exit 1
  fi
fi

cd "${COMFY_HOME}"
exec "${PYTHON}" main.py --listen "${LISTEN_HOST}" --port "${PORT}"
