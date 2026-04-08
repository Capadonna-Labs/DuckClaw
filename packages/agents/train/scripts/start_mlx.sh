#!/bin/bash
set -e
# Cargar .env: raíz del monorepo primero (canonical), luego packages/agents/train/.env si existe.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../../.." && pwd)"
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

# Checkpoints con model_type gemma4 requieren mlx-lm reciente (mlx_lm.models.gemma4).
# Si ves: ValueError: Model type gemma4 not supported → pip install -U mlx-lm en este venv.
if [ -d "$MODEL_PATH" ] && [ -f "${MODEL_PATH}/config.json" ]; then
  _GEMMA4=$(
    MODEL_PATH="$MODEL_PATH" "$PYTHON_PATH" -c "
import json, os
from pathlib import Path
p = Path(os.environ['MODEL_PATH']) / 'config.json'
d = json.loads(p.read_text(encoding='utf-8'))
print(d.get('model_type', '') or '')
" 2>/dev/null || true
  )
  if [ "$_GEMMA4" = "gemma4" ]; then
    if ! MODEL_PATH="$MODEL_PATH" "$PYTHON_PATH" -c "import mlx_lm.models.gemma4" 2>/dev/null; then
      echo "Error: El modelo en ${MODEL_PATH} es Gemma 4 (model_type=gemma4), pero este intérprete no puede cargar mlx_lm.models.gemma4."
      _pyver=$("$PYTHON_PATH" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "?")
      echo "Intérprete: $PYTHON_PATH (Python ${_pyver})"
      echo ""
      echo "Causa frecuente: mlx-lm reciente exige mlx>=0.30.4 en macOS; para Python 3.9 PyPI solo ofrece mlx hasta ~0.29.x, así que"
      echo "  pip install -U mlx-lm  NO sube de versión y Gemma 4 no llega nunca."
      echo ""
      echo "Qué hacer (elige una):"
      echo "  A) Si usas este monorepo DuckClaw: en .env pon MLX_PYTHON=<raíz-del-repo>/.venv/bin/python"
      echo "     (ese venv suele ser Python 3.10+ con mlx-lm reciente). Luego: pip install -U mlx-lm dentro de ese venv."
      echo "  B) Otro Python 3.10+: ruta real a python3.11 (whereis / brew --prefix), p. ej.:"
      echo "     /opt/homebrew/bin/python3.11 -m venv \$HOME/mlx_env311 && \$HOME/mlx_env311/bin/pip install -U pip mlx-lm"
      echo "     y MLX_PYTHON=\$HOME/mlx_env311/bin/python"
      echo "No uses rutas inventadas ni el carácter … en la shell; copia la ruta absoluta que exista (test: test -x \"\$ruta\")."
      echo "Actualizar mlx-lm en el intérprete activo:  \"$PYTHON_PATH\" -m pip install -U mlx-lm"
      echo "O desde main si hace falta: https://github.com/ml-explore/mlx-lm"
      exit 1
    fi
  fi
fi

MLX_PORT="${MLX_PORT:-8080}"
if command -v lsof >/dev/null 2>&1 && lsof -i :"${MLX_PORT}" -t >/dev/null 2>&1; then
  echo "Puerto ${MLX_PORT} ya está en uso. Ejecuta: pm2 stop MLX-Inference; lsof -ti :${MLX_PORT} | xargs kill -9; sleep 2; pm2 start MLX-Inference"
  echo "Quedando en espera para evitar reinicios en bucle (Ctrl+C o pm2 stop MLX-Inference)."
  while true; do sleep 3600; done
fi

echo "🚀 Cargando modelo desde: $MODEL_PATH"
exec "$PYTHON_PATH" -m mlx_lm.server \
  --model "$MODEL_PATH" \
  --port "${MLX_PORT}" \
  --host 0.0.0.0
