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
PYTHON_PATH="${MLX_PYTHON:-/Users/juanjosearevalocamargo/Desktop/mlx_env313/bin/python}"
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
# Gemma 4: mlx-lm >= 0.31.2 needs mlx >= 0.30.4; PyPI does not ship those mlx wheels for Python 3.9 on macOS.
if ! MODEL_PATH_CHECK="$MODEL_PATH" "$PYTHON_PATH" -c "
import json, os, sys
from pathlib import Path
from importlib import metadata as md
import importlib.util
mp = os.environ.get('MODEL_PATH_CHECK', '')
cfg = Path(mp) / 'config.json'
if not cfg.is_file():
    sys.exit(0)
if json.loads(cfg.read_text(encoding='utf-8')).get('model_type') != 'gemma4':
    sys.exit(0)
def _ver_tuple():
    p = [int(x) for x in md.version('mlx-lm').split('.')[:3]]
    return tuple((p + [0, 0, 0])[:3])
if _ver_tuple() < (0, 31, 2) or importlib.util.find_spec('mlx_lm.models.gemma4') is None:
    sys.stderr.write(
        'ERROR: checkpoint Gemma 4 requiere mlx-lm>=0.31.2 (y Python 3.10+ en macOS; con 3.9 el mlx de PyPI se queda en 0.29.x).\n'
        'Python: %s | mlx-lm: %s\n'
        'Crea venv: /opt/homebrew/bin/python3.13 -m venv ~/Desktop/mlx_env313 && '
        '~/Desktop/mlx_env313/bin/pip install \"mlx-lm>=0.31.2\". En .env: MLX_PYTHON=/ruta/absoluta/al/venv/bin/python. Luego: pm2 restart MLX-Inference\n'
        % (sys.version.split()[0], md.version('mlx-lm'))
    )
    sys.exit(1)
sys.exit(0)
"; then
  exit 1
fi
# Entrada Duckclaw: reparación ligera de JSON en tool calls Gemma4 + filtro de UserWarning del servidor dev.
export DUCKCLAW_DEBUG_LOG="${REPO_ROOT}/.cursor/debug-4a0206.log"
_MLX_ENTRY="${SCRIPT_DIR}/run_mlx_lm_server.py"
if [ ! -f "$_MLX_ENTRY" ]; then
  echo "Error: no se encontró el arranque MLX: $_MLX_ENTRY"
  exit 1
fi
if [ -n "$ADAPTER_PATH" ]; then
  echo "   + adapters LoRA: $ADAPTER_PATH"
  exec "$PYTHON_PATH" -W 'ignore::UserWarning:mlx_lm.server' "$_MLX_ENTRY" \
    --model "$MODEL_PATH" \
    --adapter-path "$ADAPTER_PATH" \
    --port "${MLX_PORT}" \
    --host 0.0.0.0
else
  exec "$PYTHON_PATH" -W 'ignore::UserWarning:mlx_lm.server' "$_MLX_ENTRY" \
    --model "$MODEL_PATH" \
    --port "${MLX_PORT}" \
    --host 0.0.0.0
fi
