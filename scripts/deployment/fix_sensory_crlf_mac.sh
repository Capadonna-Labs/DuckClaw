#!/usr/bin/env bash
set -eu
ROOT="$HOME/Desktop/duckclaw"
SCRIPT="$ROOT/integrations/sensory-node/scripts/start_sensory.sh"
tr -d '\r' < "$SCRIPT" > "${SCRIPT}.tmp"
mv "${SCRIPT}.tmp" "$SCRIPT"
chmod +x "$SCRIPT"
export PATH="/opt/homebrew/bin:$PATH"
cd "$ROOT"
pm2 restart Sensory-Node --update-env
sleep 10
pm2 status Sensory-Node
curl -sf --max-time 30 "http://100.99.72.63:8001/health" || true
echo ""
