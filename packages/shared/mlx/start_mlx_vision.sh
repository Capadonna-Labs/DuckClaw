#!/bin/bash
# Llama 3.2 11B Vision con mlx-openai-server (OpenAI-compatible).
# Uso: ./start_mlx_vision.sh
# Requiere: pip install mlx-openai-server
# OpenClaw: base URL http://127.0.0.1:8000/v1, model = el que devuelva GET /v1/models (p. ej. el id del modelo).
set -e
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "${ROOT_DIR}/.env" ] && set -a && source "${ROOT_DIR}/.env" && set +a

PYTHON_PATH="${MLX_PYTHON:-python3}"
VISION_PORT="${MLX_VISION_PORT:-8000}"
# Modelo MLX Vision 4bit (menos RAM). Alternativa: mlx-community/Llama-3.2-11B-Vision-Instruct-8bit
MODEL_PATH="${MLX_VISION_MODEL:-mlx-community/Llama-3.2-11B-Vision-Instruct-4bit}"

if ! command -v mlx-openai-server >/dev/null 2>&1; then
  echo "Instala primero: pip install mlx-openai-server"
  exit 1
fi

echo "Llama 3.2 Vision (mlx-openai-server) en http://127.0.0.1:${VISION_PORT}/v1"
exec mlx-openai-server launch \
  --model-path "$MODEL_PATH" \
  --model-type multimodal \
  --port "$VISION_PORT" \
  --host 0.0.0.0
