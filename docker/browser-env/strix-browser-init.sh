#!/bin/bash
# Arranque X11 + fluxbox + x11vnc + noVNC (puerto 6080).
# DuckClaw ejecuta el código del LLM con docker exec (python3 -c), no con /workspace/script.py:
# este script solo mantiene el display y el contenedor vivo (tail).
set -e

# 1. Pantalla virtual (display 99)
Xvfb :99 -screen 0 1280x800x24 -nolisten tcp &
export DISPLAY=:99

for _ in $(seq 1 50); do
  if [ -S "/tmp/.X11-unix/X99" ]; then
    break
  fi
  sleep 0.05
done

# 2. Gestor de ventanas (Chrome/Playwright no quedan “rotos”)
fluxbox -display :99 2>/dev/null &

# 3. VNC sin password (efímero; escucha solo en loopback del contenedor)
x11vnc -display :99 -nopw -listen localhost -xkb -ncache 10 -ncache_cr -forever \
  >>/tmp/x11vnc.log 2>&1 &

sleep 0.2

# 4. noVNC (Web UI) en 6080 — launch.sh del paquete Debian cuando exista
LAUNCH="/usr/share/novnc/utils/launch.sh"
if [ -x "$LAUNCH" ] || [ -f "$LAUNCH" ]; then
  bash "$LAUNCH" --vnc localhost:5900 --listen 6080 >>/tmp/novnc.log 2>&1 &
else
  python3 -m websockify --web=/usr/share/novnc 0.0.0.0:6080 localhost:5900 >>/tmp/websockify.log 2>&1 &
fi

# 5. El “script Python” lo lanza StrixSandboxManager con exec_run; aquí solo mantenemos el proceso principal.
exec tail -f /dev/null
