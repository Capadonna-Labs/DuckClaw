#!/bin/bash
# Servidor OpenAI-compatible para **visión** (multimodal), en un puerto distinto de MLX_PORT (mlx_lm texto).
# Gateway DuckClaw suele usar Uvicorn en 8000 → no uses 8000 aquí salvo que muevas el API.
#
# Requiere: ``mlx-openai-server`` desde PyPI con Python **>=3.11 y <3.13** (metadata del paquete).
# Tu venv de ``mlx_lm`` (MLX_PYTHON) suele ser **3.13+** → ahí **no** instala mlx-openai-server. Usa un venv aparte:
#   Dos comandos separados (o un solo renglón con &&). No escribas « y » entre ellos en la misma línea.
#   /opt/homebrew/bin/python3.12 -m venv ~/mlx_vision312
#   ~/mlx_vision312/bin/pip install mlx-openai-server
# En .env:
#   MLX_VISION_PYTHON=/ruta/mlx_vision312/bin/python
# El .venv DuckClaw en 3.14 tampoco sirve (outlines-core sin wheel / Rust).
# También en .env (mismo que start_mlx.sh):
#   MLX_PORT=8080                          # mlx_lm texto (puede ser Python 3.13)
#   MLX_VISION_PORT=8081                  # este script (default 8081)
#   DUCKCLAW_VLM_MLX_BASE_URL=http://127.0.0.1:8081/v1
#   DUCKCLAW_VLM_MLX_MODEL=<id que liste GET /v1/models>
# Opcional: VLM_MLX_PORT=8081 (sin URL completa) si no defines DUCKCLAW_VLM_MLX_BASE_URL.
#
# Uso desde raíz del repo:
#   bash packages/agents/train/scripts/start_mlx_vision.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
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

# Visión: venv 3.11–3.12. Texto mlx_lm puede seguir en MLX_PYTHON 3.13+.
PYTHON_PATH="${MLX_VISION_PYTHON:-${MLX_PYTHON:-python3}}"
if command -v "${PYTHON_PATH}" >/dev/null 2>&1; then
  PYTHON_PATH="$(command -v "${PYTHON_PATH}")"
fi
# Binarios del venv elegido (console script mlx-openai-server).
_PY_BINDIR="$(cd "$(dirname "$PYTHON_PATH")" && pwd)"
export PATH="${_PY_BINDIR}:${PATH}"

VISION_PORT="${MLX_VISION_PORT:-${VLM_MLX_PORT:-8081}}"
# Modelo MLX Vision 4bit. Alineado con DUCKCLAW_VLM_MLX_MODEL / MLX_VISION_MODEL si lo exportas.
MODEL_PATH="${MLX_VISION_MODEL:-mlx-community/Llama-3.2-11B-Vision-Instruct-4bit}"

if ! "$PYTHON_PATH" -c 'import sys; sys.exit(0 if sys.version_info < (3, 13) else 1)' 2>/dev/null; then
  _v="$("$PYTHON_PATH" -c 'import sys; print("%s.%s.%s" % sys.version_info[:3])' 2>/dev/null || echo "?")"
  echo "Error: mlx-openai-server en PyPI declara Requires-Python <3.13 (p. ej. 1.7.1)."
  echo "Intérprete actual: ${_v} (${PYTHON_PATH})"
  if [ -z "${MLX_VISION_PYTHON:-}" ]; then
    echo "MLX_PYTHON es probablemente 3.13+ para mlx_lm. Crea un venv **solo** con Python 3.12 (dos líneas o usa &&):"
    echo "  /opt/homebrew/bin/python3.12 -m venv \"\${HOME}/mlx_vision312\""
    echo "  \"\${HOME}/mlx_vision312/bin/pip\" install mlx-openai-server"
    echo "(No pegues la palabra «y» entre esos comandos; si falló antes: rm -rf \"\${HOME}/mlx_vision312\"; luego repite los dos pasos.)"
    echo "En .env: MLX_VISION_PYTHON=\${HOME}/mlx_vision312/bin/python"
  else
    echo "Corrije MLX_VISION_PYTHON a un python 3.11 o 3.12."
  fi
  exit 1
fi

if "$PYTHON_PATH" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
  :
else
  echo "Error: se requiere Python >=3.11 para mlx-openai-server (${PYTHON_PATH})."
  exit 1
fi

_TEXT_PORT="${MLX_PORT:-8080}"
if [ "${VISION_PORT}" = "${_TEXT_PORT}" ]; then
  echo "Error: MLX_VISION_PORT/VLM_MLX_PORT (${VISION_PORT}) no puede coincidir con MLX_PORT (mlx_lm solo texto)."
  echo "Usa p. ej. MLX_PORT=8080 y MLX_VISION_PORT=8081 y DUCKCLAW_VLM_MLX_BASE_URL=http://127.0.0.1:8081/v1"
  exit 1
fi
if [ "${VISION_PORT}" = "8000" ]; then
  echo "Advertencia: puerto 8000 suele ser el API Gateway DuckClaw; considera MLX_VISION_PORT=8081."
fi

if command -v mlx-openai-server >/dev/null 2>&1; then
  _MLX_OAI=(mlx-openai-server)
elif [ -x "${_PY_BINDIR}/mlx-openai-server" ]; then
  _MLX_OAI=("${_PY_BINDIR}/mlx-openai-server")
else
  echo "No se encontró mlx-openai-server en PATH (tras añadir ${_PY_BINDIR})."
  echo "Instala en el mismo intérprete que MLX_VISION_PYTHON (Python 3.11–3.12):"
  echo "  \"${PYTHON_PATH}\" -m pip install mlx-openai-server"
  exit 1
fi

echo "[start_mlx_vision] REPO_ROOT=${REPO_ROOT}"
echo "[start_mlx_vision] python=${PYTHON_PATH}"
echo "[start_mlx_vision] Visión OpenAI-compat: http://127.0.0.1:${VISION_PORT}/v1  modelo=${MODEL_PATH}"
echo "[start_mlx_vision] En .env: DUCKCLAW_VLM_MLX_BASE_URL=http://127.0.0.1:${VISION_PORT}/v1"
echo "[start_mlx_vision] Reinicia DuckClaw-Gateway tras cambiar .env."
exec "${_MLX_OAI[0]}" launch \
  --model-path "$MODEL_PATH" \
  --model-type multimodal \
  --port "$VISION_PORT" \
  --host 0.0.0.0
