/** Helpers bash: espera PM2/health sin sleeps fijos. */

export function pm2WaitShellPreamble(): string {
  return `
wait_pm2_stopped() {
  local name="$1"
  local timeout="\${2:-15}"
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if ! pm2 describe "$name" >/dev/null 2>&1; then
      echo "PM2_STOPPED:$name (absent)"
      return 0
    fi
    if pm2 describe "$name" 2>/dev/null | grep -qE 'status.*(stopped|errored)'; then
      echo "PM2_STOPPED:$name"
      return 0
    fi
    sleep 0.5
  done
  echo "PM2_STOP_TIMEOUT:$name"
  return 1
}

wait_pm2_online() {
  local name="$1"
  local timeout="\${2:-30}"
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if pm2 describe "$name" 2>/dev/null | grep -qE 'status.*online'; then
      echo "PM2_ONLINE:$name"
      return 0
    fi
    sleep 0.5
  done
  echo "PM2_ONLINE_TIMEOUT:$name"
  return 1
}

wait_gateway_health() {
  local url="\${DUCKCLAW_GATEWAY_URL:-http://127.0.0.1:8000}/health"
  local timeout="\${1:-45}"
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "GATEWAY_HEALTH_OK $url"
      return 0
    fi
    sleep 0.5
  done
  echo "GATEWAY_HEALTH_TIMEOUT $url"
  return 1
}

heal_pm2_corrupt_db_writer() {
  if ! pm2 describe DuckClaw-DB-Writer >/dev/null 2>&1; then
    return 0
  fi
  if pm2 describe DuckClaw-DB-Writer 2>/dev/null | grep -qE 'script path.*services/db-writer/main\\.py'; then
    echo "PM2_HEAL: DuckClaw-DB-Writer corrupt entry (main.py as script); deleting"
    pm2 delete DuckClaw-DB-Writer 2>/dev/null || true
  fi
}
`.trim();
}
