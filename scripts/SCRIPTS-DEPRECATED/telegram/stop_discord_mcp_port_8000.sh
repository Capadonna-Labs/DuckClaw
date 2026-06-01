#!/usr/bin/env bash
# Mata solo procesos que escuchan en 127.0.0.1:8000 y cuyo comando incluye discord_mcp.
# Así Funnel (proxy http://127.0.0.1:8000) y curl local llegan a Duckclaw en *:8000.
set -euo pipefail
if ! command -v lsof >/dev/null 2>&1; then
  echo "lsof no disponible" >&2
  exit 1
fi
pid_list=$(lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | awk '/127\.0\.0\.1:8000/ {print $2}' | sort -u)
if [[ -z "${pid_list}" ]]; then
  echo "No hay LISTEN en 127.0.0.1:8000; nada que hacer."
  exit 0
fi
for pid in ${pid_list}; do
  cmd=$(ps -p "${pid}" -o command= 2>/dev/null || true)
  if echo "${cmd}" | grep -qE 'discord_mcp'; then
    echo "Deteniendo PID ${pid} (discord_mcp en 127.0.0.1:8000)"
    kill "${pid}" 2>/dev/null || true
  else
    echo "PID ${pid} escucha 127.0.0.1:8000 pero no parece discord_mcp; no lo toco: ${cmd:0:160}"
  fi
done
