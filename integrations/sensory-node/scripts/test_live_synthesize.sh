#!/usr/bin/env bash
set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH:-/usr/bin:/bin}"

export VOICE_ID="${DUCKCLAW_SENSORY_TEST_VOICE_ID:-default_assistant}"

python3 - <<PY
import json
import os
json.dump(
    {"text": "Hola prueba", "voice_id": os.environ["VOICE_ID"], "output_format": "wav"},
    open("/tmp/tts_req.json", "w"),
)
PY

curl -s -w "\nHTTP:%{http_code}\n" \
  -X POST "http://100.99.72.63:8001/api/v1/sensory/synthesize" \
  -H "Content-Type: application/json" \
  --data-binary @/tmp/tts_req.json \
  -o /tmp/tts_resp.json

python3 "$(dirname "$0")/peak_from_tts_json.py" < /tmp/tts_resp.json
