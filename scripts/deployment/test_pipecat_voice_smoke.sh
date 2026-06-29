#!/usr/bin/env bash
# Manual smoke checklist for DuckClaw-Voice (Pipecat SmallWebRTC + worker default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
exec bash integrations/pipecat-voice/scripts/test_pipecat_voice_smoke.sh
