#!/usr/bin/env bash
# Manual smoke checklist for DuckClaw-Voice (Pipecat SmallWebRTC + worker default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "==> DuckClaw-Voice smoke (manual)"
echo "Preconditions:"
echo "  - DuckClaw-Gateway running with DUCKCLAW_ADMIN_API_KEY"
echo "  - DUCKCLAW_VOICE_ENABLED=true in .env"
echo "  - DEEPGRAM_API_KEY and CARTESIA_API_KEY set"
echo "  - DUCKCLAW_VOICE_GATEWAY_ADMIN_KEY matches gateway admin key"
echo ""

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env 2>/dev/null || true
  set +a
fi

HOST="${DUCKCLAW_VOICE_BIND_HOST:-127.0.0.1}"
PORT="${DUCKCLAW_VOICE_PORT:-8012}"
BASE="http://${HOST}:${PORT}"

echo "==> Unit tests (graph bridge, no pipecat required)"
uv run --project integrations/pipecat-voice --extra dev pytest integrations/pipecat-voice/tests/test_graph_bridge.py integrations/pipecat-voice/tests/test_session_context.py integrations/pipecat-voice/tests/test_progress_tts.py -q

echo ""
echo "==> Health (service must be running: pm2 start config/ecosystem.voice.config.cjs)"
if curl -sf "${BASE}/health" >/dev/null 2>&1; then
  curl -s "${BASE}/health" | head -c 500
  echo ""
  echo "OK: /health"
else
  echo "SKIP: voice service not reachable at ${BASE}/health"
  echo "Start with: pm2 start config/ecosystem.voice.config.cjs"
fi

echo ""
echo "==> Manual WebRTC steps"
echo "  1. Open ${BASE}/client/ in Chrome/Edge"
echo "  2. Allow microphone; speak 3+ turns (es/en) with worker default"
echo "  3. Confirm spoken replies via Cartesia (not Sensory batch)"
echo "  4. Check conversation_traces for chat_id voice-* matching session"
echo ""
echo "Optional: worker error turn — graph must speak worker message, not progress phrase alone."
