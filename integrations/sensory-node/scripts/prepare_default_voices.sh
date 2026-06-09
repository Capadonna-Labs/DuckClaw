#!/usr/bin/env bash
# Offline bootstrap: generate macOS TTS refs and encode voice tensors (dev/lab only).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="$(cd "$ROOT/../.." && pwd)"
VOICES="$ROOT/voices"
REFS="$VOICES/refs"
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-}"

cd "$REPO"
mkdir -p "$REFS"

prepare_one() {
  local voice_id="$1"
  local voice_name="$2"
  local ref_text="$3"
  local aiff="$REFS/${voice_id}.aiff"
  local wav="$REFS/${voice_id}.wav"

  say -v "$voice_name" -o "$aiff" "$ref_text"
  afconvert -f WAVE -d LEI16 "$aiff" "$wav"
  uv run --project integrations/sensory-node python integrations/sensory-node/scripts/prepare_voice.py \
    --voice-id "$voice_id" \
    --ref-audio "$wav" \
    --ref-text "$ref_text"
}

prepare_one leila_assistant Monica "Hola soy Leila tu asistente de DuckClaw"
prepare_one finanz_alert Paulina "Alerta financiera DuckClaw revisa tu portafolio"
prepare_one campus_legal_main Jorge "Asesoria legal campus DuckClaw"

ls -la "$VOICES"/*.safetensors
