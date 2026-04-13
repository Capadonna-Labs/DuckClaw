#!/bin/bash
set -e
# Cargar .env: raíz del monorepo primero (canonical), luego packages/agents/train/.env si existe.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# Preferir raíz git (robusto si el repo se mueve o hay symlinks).
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
if command -v git >/dev/null 2>&1; then
  _GIT_ROOT="$(git -C "${REPO_ROOT}" rev-parse --show-toplevel 2>/dev/null || true)"
  if [ -n "${_GIT_ROOT}" ] && [ -f "${_GIT_ROOT}/.env" ]; then
    REPO_ROOT="${_GIT_ROOT}"
  fi
fi
for envfile in "${REPO_ROOT}/.env" "${ROOT_DIR}/.env"; do
  if [ -f "${envfile}" ]; then
    set -a
    # shellcheck source=/dev/null
    source "${envfile}"
    set +a
  fi
done
# Rutas: desde .env o valores por defecto
PYTHON_PATH="${MLX_PYTHON:-/Users/juanjosearevalocamargo/Desktop/mlx_env/bin/python}"
MODEL_PATH="${MLX_MODEL_PATH:-/Users/juanjosearevalocamargo/Desktop/models/Slayer-8B-V1}"

if [ ! -x "$PYTHON_PATH" ]; then
  echo "Error: Python no encontrado o no ejecutable: $PYTHON_PATH. Exporta MLX_PYTHON si usas otro venv."
  exit 1
fi
if [ ! -d "$MODEL_PATH" ] && [ ! -f "$MODEL_PATH" ]; then
  echo "Error: Modelo no encontrado en: $MODEL_PATH. Exporta MLX_MODEL_PATH si usas otra ruta."
  exit 1
fi

MLX_PORT="${MLX_PORT:-8080}"
if command -v lsof >/dev/null 2>&1 && lsof -i :"${MLX_PORT}" -t >/dev/null 2>&1; then
  echo "Puerto ${MLX_PORT} ya está en uso. Ejecuta: pm2 stop MLX-Inference; lsof -ti :${MLX_PORT} | xargs kill -9; sleep 2; pm2 start MLX-Inference"
  echo "Quedando en espera para evitar reinicios en bucle (Ctrl+C o pm2 stop MLX-Inference)."
  while true; do sleep 3600; done
fi

ADAPTER_PATH="${MLX_ADAPTER_PATH:-}"
if [ -n "$ADAPTER_PATH" ] && [ "${ADAPTER_PATH#/}" = "$ADAPTER_PATH" ]; then
  ADAPTER_PATH="${REPO_ROOT}/${ADAPTER_PATH}"
fi
if [ -n "$ADAPTER_PATH" ] && [ ! -d "$ADAPTER_PATH" ] && [ ! -f "$ADAPTER_PATH" ]; then
  echo "Advertencia: MLX_ADAPTER_PATH no existe ($ADAPTER_PATH); arrancando sin LoRA."
  ADAPTER_PATH=""
fi

echo "[start_mlx] REPO_ROOT=${REPO_ROOT}"
echo "[start_mlx] MLX_ADAPTER_PATH(raw)=${MLX_ADAPTER_PATH:-<unset>}"
if [ -n "$ADAPTER_PATH" ]; then
  echo "[start_mlx] LoRA: ENABLED (--adapter-path) -> ${ADAPTER_PATH}"
else
  echo "[start_mlx] LoRA: DISABLED (define MLX_ADAPTER_PATH en .env del repo o corrige la ruta; pm2 logs debe mostrar ENABLED tras reinicio)"
fi
echo "🚀 Cargando modelo desde: $MODEL_PATH"
if [ -n "$ADAPTER_PATH" ]; then
  echo "   + adapters LoRA: $ADAPTER_PATH"
  exec "$PYTHON_PATH" -m mlx_lm.server \
    --model "$MODEL_PATH" \
    --adapter-path "$ADAPTER_PATH" \
    --port "${MLX_PORT}" \
    --host 0.0.0.0
else
  exec "$PYTHON_PATH" -m mlx_lm.server \
    --model "$MODEL_PATH" \
    --port "${MLX_PORT}" \
    --host 0.0.0.0
fi
