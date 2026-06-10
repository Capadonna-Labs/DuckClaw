#!/usr/bin/env bash
# Sync DuckClaw monorepo on VPS after push to main (manual or GitHub Actions CD).
set -euo pipefail

DUCKCLAW_ROOT="${DUCKCLAW_ROOT:-/root/duckclaw}"
export PATH="/root/.local/bin:/usr/local/bin:${PATH}"

log() { echo "[sync-duckclaw] $*"; }

if [[ ! -d "${DUCKCLAW_ROOT}/.git" ]]; then
  log "ERROR: no git repo at ${DUCKCLAW_ROOT}"
  exit 1
fi

cd "${DUCKCLAW_ROOT}"

dirty="$(git status --porcelain)"
if [[ -n "${dirty}" ]]; then
  log "WARN: working tree dirty; stashing tracked + untracked"
  git stash push -u -m "sync_duckclaw_main-$(date +%s)" || true
fi

log "fetch + pull main"
git fetch origin main
git pull --ff-only origin main

log "uv sync"
uv sync

log "restart gateway"
if pm2 pid DuckClaw-Gateway >/dev/null 2>&1; then
  pm2 restart DuckClaw-Gateway DuckClaw-DB-Writer --update-env
elif systemctl is-active --quiet capadonna-duckclaw-gateway 2>/dev/null; then
  systemctl restart capadonna-duckclaw-gateway capadonna-duckclaw-db-writer
else
  log "ERROR: ni PM2 DuckClaw-Gateway ni systemd capadonna-duckclaw-gateway activos"
  exit 1
fi

log "health check"
for _ in 1 2 3 4 5; do
  if curl -sf --max-time 15 "http://127.0.0.1:8000/health" >/dev/null; then
    break
  fi
  sleep 2
done
curl -sf --max-time 15 "http://127.0.0.1:8000/health" >/dev/null

sha="$(git rev-parse --short HEAD)"
log "sync ok ${sha}"
