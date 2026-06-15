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

PYTHON_PATH="${MLX_PYTHON:-}"
if [ -z "${PYTHON_PATH}" ]; then
  echo "Error: define MLX_PYTHON in ${REPO_ROOT}/.env."
  exit 1
fi

MODEL_PATH="${MLX_MODEL_PATH:-}"
if [ -z "${MODEL_PATH}" ]; then
  echo "Error: define MLX_MODEL_PATH in ${REPO_ROOT}/.env."
  exit 1
fi

if [ ! -x "${PYTHON_PATH}" ]; then
  echo "Error: Python not found or not executable: ${PYTHON_PATH}."
  exit 1
fi

if [ ! -d "${MODEL_PATH}" ] && [ ! -f "${MODEL_PATH}" ]; then
  echo "Error: model not found at ${MODEL_PATH}."
  exit 1
fi

MLX_PORT="${MLX_PORT:-8080}"
if command -v lsof >/dev/null 2>&1 && lsof -i :"${MLX_PORT}" -t >/dev/null 2>&1; then
  echo "Port ${MLX_PORT} is already in use; stop the existing MLX process first."
  while true; do sleep 3600; done
fi

ADAPTER_PATH="${MLX_ADAPTER_PATH:-}"
if [ -n "${ADAPTER_PATH}" ] && [ "${ADAPTER_PATH#/}" = "${ADAPTER_PATH}" ]; then
  ADAPTER_PATH="${REPO_ROOT}/${ADAPTER_PATH}"
fi
if [ -n "${ADAPTER_PATH}" ] && [ ! -d "${ADAPTER_PATH}" ] && [ ! -f "${ADAPTER_PATH}" ]; then
  echo "Warning: MLX_ADAPTER_PATH does not exist (${ADAPTER_PATH}); starting without LoRA."
  ADAPTER_PATH=""
fi

echo "[start_mlx] REPO_ROOT=${REPO_ROOT}"
echo "[start_mlx] model=${MODEL_PATH}"
if [ -n "${ADAPTER_PATH}" ]; then
  echo "[start_mlx] LoRA enabled: ${ADAPTER_PATH}"
else
  echo "[start_mlx] LoRA disabled"
fi

MLX_ENTRY="${SCRIPT_DIR}/run_mlx_lm_server.py"
if [ ! -f "${MLX_ENTRY}" ]; then
  echo "Error: MLX server entrypoint not found: ${MLX_ENTRY}"
  exit 1
fi

if [ -n "${ADAPTER_PATH}" ]; then
  exec "${PYTHON_PATH}" -W 'ignore::UserWarning:mlx_lm.server' "${MLX_ENTRY}" \
    --model "${MODEL_PATH}" \
    --adapter-path "${ADAPTER_PATH}" \
    --port "${MLX_PORT}" \
    --host 0.0.0.0
else
  exec "${PYTHON_PATH}" -W 'ignore::UserWarning:mlx_lm.server' "${MLX_ENTRY}" \
    --model "${MODEL_PATH}" \
    --port "${MLX_PORT}" \
    --host 0.0.0.0
fi
