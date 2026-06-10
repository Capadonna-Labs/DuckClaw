#!/usr/bin/env bash
# PM2 launcher for sensory_node on Mac mini (Tailscale bind only).
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"

_read_env() {
  local key="$1"
  local default="${2:-}"
  local line
  line="$(grep -m1 "^${key}=" .env 2>/dev/null || true)"
  if [[ -z "$line" ]]; then
    printf '%s' "$default"
    return
  fi
  printf '%s' "${line#${key}=}"
}

if [[ -f .env ]]; then
  export DUCKCLAW_SENSORY_BIND_HOST="$(_read_env DUCKCLAW_SENSORY_BIND_HOST)"
  export DUCKCLAW_SENSORY_PORT="$(_read_env DUCKCLAW_SENSORY_PORT 8001)"
  export DUCKCLAW_SENSORY_TTS_MODEL="$(_read_env DUCKCLAW_SENSORY_TTS_MODEL mlx-community/OmniVoice-bf16)"
  export DUCKCLAW_SENSORY_TTS_TIMEOUT_MS="$(_read_env DUCKCLAW_SENSORY_TTS_TIMEOUT_MS 60000)"
  export DUCKCLAW_SENSORY_TTS_MAX_CHARS="$(_read_env DUCKCLAW_SENSORY_TTS_MAX_CHARS 1400)"
  export DUCKCLAW_SENSORY_TTS_MAX_DURATION_SEC="$(_read_env DUCKCLAW_SENSORY_TTS_MAX_DURATION_SEC 90)"
  export DUCKCLAW_SENSORY_TTS_NUM_STEPS="$(_read_env DUCKCLAW_SENSORY_TTS_NUM_STEPS 32)"
  export DUCKCLAW_SENSORY_AUDIO_TOKENIZER_MODEL="$(_read_env DUCKCLAW_SENSORY_AUDIO_TOKENIZER_MODEL mlx-community/OmniVoice-4bit)"
fi

BIND="${DUCKCLAW_SENSORY_BIND_HOST:?Set DUCKCLAW_SENSORY_BIND_HOST to your Tailscale IP (e.g. 100.x.y.z)}"
PORT="${DUCKCLAW_SENSORY_PORT:-8001}"
exec uv run --project integrations/sensory-node \
  uvicorn duckclaw_sensory_node.main:app \
  --host "$BIND" \
  --port "$PORT" \
  --log-level info
