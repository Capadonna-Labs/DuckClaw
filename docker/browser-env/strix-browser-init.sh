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

# Fondo sólido antes de fluxbox; ``feh`` en la imagen evita que ``fbsetbg`` abra xmessage
# (“can't find an app to set the wallpaper”).
if command -v xsetroot >/dev/null 2>&1; then
  xsetroot -solid "#252525" 2>/dev/null || true
fi

# 2. Gestor de ventanas (Chrome/Playwright no quedan “rotos”)
fluxbox -display :99 2>/dev/null &

# 3. VNC sin password (efímero; escucha solo en loopback del contenedor)
x11vnc -display :99 -nopw -listen localhost -xkb -ncache 10 -ncache_cr -forever \
  >>/tmp/x11vnc.log 2>&1 &

sleep 0.2

# 4. noVNC (Web UI) en 6080
# - En bookworm el paquete ``novnc`` puede no traer ``utils/launch.sh`` (solo assets bajo /usr/share/novnc).
# - La imagen base ``python:*-slim`` define ``python3`` -> /usr/local/bin/python3, que **no** tiene el
#   módulo ``websockify`` instalado por apt (``python3-websockify`` va con /usr/bin/python3).
LAUNCH="/usr/share/novnc/utils/launch.sh"
NOVNC_WEB="/usr/share/novnc"
if [ -f "$LAUNCH" ]; then
  bash "$LAUNCH" --vnc localhost:5900 --listen 6080 >>/tmp/novnc.log 2>&1 &
elif command -v websockify >/dev/null 2>&1; then
  websockify --web="$NOVNC_WEB" 0.0.0.0:6080 localhost:5900 >>/tmp/websockify.log 2>&1 &
else
  /usr/bin/python3 -m websockify --web="$NOVNC_WEB" 0.0.0.0:6080 localhost:5900 >>/tmp/websockify.log 2>&1 &
fi

# 5. Ventana de Chromium por defecto (perfil distinto a /workspace/chrome_profile usado por Playwright).
#    Así noVNC no muestra solo Fluxbox vacío hasta que corra automatización.
#    Desactivar: DUCKCLAW_BROWSER_IDLE_CHROMIUM=0
if [ "${DUCKCLAW_BROWSER_IDLE_CHROMIUM:-1}" != "0" ] && command -v chromium >/dev/null 2>&1; then
  mkdir -p /workspace/chrome_idle_vnc
  chromium --no-sandbox --disable-dev-shm-usage \
    --user-data-dir=/workspace/chrome_idle_vnc \
    --window-size=1280,720 \
    --window-position=0,0 \
    about:blank >>/tmp/chromium_idle.log 2>&1 &
fi

# 6. El “script Python” lo lanza StrixSandboxManager con exec_run; aquí solo mantenemos el proceso principal.
exec tail -f /dev/null
