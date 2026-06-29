#!/usr/bin/env bash
# PM2 launcher for DuckClaw-Voice (Pipecat SmallWebRTC + graph bridge).
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
  export DUCKCLAW_VOICE_ENABLED="$(_read_env DUCKCLAW_VOICE_ENABLED false)"
  export DUCKCLAW_VOICE_BIND_HOST="$(_read_env DUCKCLAW_VOICE_BIND_HOST 127.0.0.1)"
  export DUCKCLAW_VOICE_PORT="$(_read_env DUCKCLAW_VOICE_PORT 8012)"
  export DUCKCLAW_VOICE_GATEWAY_URL="$(_read_env DUCKCLAW_VOICE_GATEWAY_URL http://127.0.0.1:8000)"
  export DUCKCLAW_VOICE_GATEWAY_ADMIN_KEY="$(_read_env DUCKCLAW_VOICE_GATEWAY_ADMIN_KEY)"
  export DUCKCLAW_VOICE_DEFAULT_WORKER="$(_read_env DUCKCLAW_VOICE_DEFAULT_WORKER default)"
  export DUCKCLAW_VOICE_DEFAULT_TENANT="$(_read_env DUCKCLAW_VOICE_DEFAULT_TENANT default)"
  export DUCKCLAW_VOICE_TRANSPORT="$(_read_env DUCKCLAW_VOICE_TRANSPORT small_webrtc)"
  export DUCKCLAW_VOICE_STT_PROVIDER="$(_read_env DUCKCLAW_VOICE_STT_PROVIDER sensory_adapter)"
  export DUCKCLAW_VOICE_TTS_PROVIDER="$(_read_env DUCKCLAW_VOICE_TTS_PROVIDER sensory_adapter)"
  export DUCKCLAW_SENSORY_BASE_URL="$(_read_env DUCKCLAW_SENSORY_BASE_URL http://127.0.0.1:8001)"
  export DUCKCLAW_TTS_DEFAULT_VOICE_ID="$(_read_env DUCKCLAW_TTS_DEFAULT_VOICE_ID default)"
  export DUCKCLAW_TTS_VOICE_MAP="$(_read_env DUCKCLAW_TTS_VOICE_MAP)"
  export DEEPGRAM_API_KEY="$(_read_env DEEPGRAM_API_KEY)"
  export CARTESIA_API_KEY="$(_read_env CARTESIA_API_KEY)"
fi

ENABLED="${DUCKCLAW_VOICE_ENABLED:-false}"
enabled_lc="$(printf '%s' "$ENABLED" | tr '[:upper:]' '[:lower:]')"
case "$enabled_lc" in
  1|true|yes|on)
    ;;
  *)
    echo "DuckClaw-Voice disabled (DUCKCLAW_VOICE_ENABLED=${ENABLED}); exit 0"
    exit 0
    ;;
esac

BIND="${DUCKCLAW_VOICE_BIND_HOST:-127.0.0.1}"
PORT="${DUCKCLAW_VOICE_PORT:-8012}"
exec uv run --project integrations/pipecat-voice --extra realtime --extra dev \
  uvicorn duckclaw_pipecat.main:app \
  --host "$BIND" \
  --port "$PORT" \
  --log-level info
