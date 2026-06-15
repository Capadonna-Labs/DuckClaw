#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAIN_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../../.." && pwd)"

if command -v git >/dev/null 2>&1; then
  GIT_ROOT="$(git -C "${REPO_ROOT}" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "${GIT_ROOT}" ] && [ -f "${GIT_ROOT}/.env" ]; then
    REPO_ROOT="${GIT_ROOT}"
  fi
fi

for envfile in "${REPO_ROOT}/.env" "${TRAIN_DIR}/.env"; do
  if [ -f "${envfile}" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${envfile}"
    set +a
  fi
done

PYTHON_PATH="${MLX_VISION_PYTHON:-${MLX_PYTHON:-python3}}"
if command -v "${PYTHON_PATH}" >/dev/null 2>&1; then
  PYTHON_PATH="$(command -v "${PYTHON_PATH}")"
fi

PY_BINDIR="$(cd "$(dirname "${PYTHON_PATH}")" && pwd)"
export PATH="${PY_BINDIR}:${PATH}"

VISION_PORT="${MLX_VISION_PORT:-${VLM_MLX_PORT:-8081}}"
MODEL_PATH="${MLX_VISION_MODEL:-mlx-community/Llama-3.2-11B-Vision-Instruct-4bit}"

if ! "${PYTHON_PATH}" -c 'import sys; sys.exit(0 if sys.version_info < (3, 13) else 1)' 2>/dev/null; then
  echo "Error: mlx-openai-server currently requires Python <3.13."
  echo "Set MLX_VISION_PYTHON to a Python 3.11 or 3.12 virtualenv."
  exit 1
fi

if ! "${PYTHON_PATH}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  echo "Error: MLX vision serving requires Python >=3.11."
  exit 1
fi

TEXT_PORT="${MLX_PORT:-8080}"
if [ "${VISION_PORT}" = "${TEXT_PORT}" ]; then
  echo "Error: vision port (${VISION_PORT}) cannot match MLX_PORT (${TEXT_PORT})."
  exit 1
fi

if command -v mlx-openai-server >/dev/null 2>&1; then
  MLX_OPENAI_SERVER="$(command -v mlx-openai-server)"
elif [ -x "${PY_BINDIR}/mlx-openai-server" ]; then
  MLX_OPENAI_SERVER="${PY_BINDIR}/mlx-openai-server"
else
  echo "Error: mlx-openai-server not found for ${PYTHON_PATH}."
  echo "Install it with: ${PYTHON_PATH} -m pip install mlx-openai-server"
  exit 1
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"${VISION_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Error: TCP port ${VISION_PORT} is already listening."
  lsof -nP -iTCP:"${VISION_PORT}" -sTCP:LISTEN || true
  exit 1
fi

echo "[start_mlx_vision] REPO_ROOT=${REPO_ROOT}"
echo "[start_mlx_vision] python=${PYTHON_PATH}"
echo "[start_mlx_vision] http://127.0.0.1:${VISION_PORT}/v1 model=${MODEL_PATH}"

exec "${MLX_OPENAI_SERVER}" launch \
  --model-path "${MODEL_PATH}" \
  --model-type multimodal \
  --port "${VISION_PORT}" \
  --host 0.0.0.0
