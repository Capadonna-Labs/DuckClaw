# Strix Browser Sandbox — noVNC y `get_browser_session_url`

## Objetivo

Permitir que el usuario vea en tiempo real el escritorio virtual donde corre Playwright en el contenedor **browser-env**, mediante **noVNC**, con URL firmada por **token** y **TTL** corto, sin exponer VNC sin autenticación en internet abierto.

## Comportamiento

1. **Sesión estable:** el `session_id` del sandbox browser se deriva del `chat_id` (sanitizado) para reutilizar el mismo contenedor `strix_sandbox_<session_id>` por conversación.
2. **Puerto en el host:** Docker publica `6080/tcp` del contenedor a un **puerto aleatorio** en `127.0.0.1` del host (evita colisiones entre chats).
3. **Token:** cada sesión activa obtiene un token opaco (p. ej. `secrets.token_urlsafe`); el registro `token → (puerto host, expiración)` vive en memoria del proceso del gateway.
4. **TTL:** 10 minutos desde el último “touch” (ejecución de `run_browser_sandbox` o `get_browser_session_url`). Al expirar se llama a `StrixSandboxManager.cleanup(session_id)` y se invalida el token.
5. **Orden antes de ejecutar código en el browser:** el worker LangGraph llama a `ensure_browser_novnc_session(worker_id, session_id)` **antes** de `tool.invoke(run_browser_sandbox)`: levanta o reutiliza el contenedor y registra noVNC (equivalente a los pasos previos a `exec_run` en `StrixSandboxManager.execute`). Así el usuario puede recibir el enlace por Telegram (heartbeat de herramienta o DM opcional) **antes** de que corra el script Playwright.
6. **URLs devueltas al LLM:**
   - `vnc_url` en el JSON de `run_browser_sandbox` cuando hay publicación de puerto y red `bridge`.
   - `get_browser_session_url` devuelve la misma clase de URL si el contenedor sigue vivo.
7. **Proxy HTTP/WebSocket:** rutas bajo `/api/v1/sandbox/novnc/view/{token}/...` en el API Gateway reenvían a `http://127.0.0.1:<puerto>/...` y el WebSocket `/websockify` hacia el contenedor.

## URL pública (Telegram / móvil)

- **`DUCKCLAW_PUBLIC_URL`:** base HTTPS (o HTTP solo en dev) para construir `vnc_url` (sin depender de `localhost` en el teléfono).
- **Tailscale Funnel:** opción recomendada para exponer el **mismo puerto** donde escucha el API Gateway (p. ej. 8000) con HTTPS, sin nginx/Let’s Encrypt en el borde. Funnel **no** reemplaza el proxy con token: solo hace ingress hasta el gateway.

## Seguridad

- noVNC en el contenedor sigue **sin contraseña VNC**; la protección es **token opaco + TTL + red aislada** y **no** enlazar el proxy en entornos públicos sin HTTPS.
- Rutas `/api/v1/sandbox/novnc/` deben quedar **exentas** de `X-Tailscale-Auth-Key` si el usuario abre el enlace en un navegador sin esa cabecera (el token sustituye la autenticación para ese recurso).

## Variables de entorno

- `STRIX_BROWSER_PUBLISH_NOVNC=1` — publicar puerto 6080→host (sigue siendo necesario para que el proxy local alcance el contenedor).
- `DUCKCLAW_PUBLIC_URL` — base para `vnc_url` (p. ej. `https://tu-nodo.ts.net` vía Funnel).
- `DUCKCLAW_BROWSER_NOVNC_PRE_DM` — si está en `1` / `true` / `always`, y el **heartbeat por chat** está desactivado, se envía igual un DM corto con el enlace noVNC antes de ejecutar `run_browser_sandbox` (cuando hay URL). Con heartbeat activo, el enlace va en el mensaje de progreso de herramienta (no hace falta esta variable).

## Visibilidad en noVNC (Playwright)

- Chromium debe ejecutarse en modo **headed** (`headless=False` en `launch` / `launch_persistent_context`) para pintar en el Xvfb interno (`DISPLAY=:99`). Si el script usa `headless=True`, no hay ventana en el framebuffer y noVNC solo muestra el escritorio (p. ej. Fluxbox) sin navegador.
- El gateway puede **sustituir** en el código enviado al contenedor `headless=True` → `headless=False` salvo `DUCKCLAW_BROWSER_PLAYWRIGHT_HEADLESS=1` en el entorno del proceso (opt-out para depuración o cuando no importe VNC).

## Limitaciones

- Con `network_mode=none` no hay mapeo de puertos útil hacia el host: `vnc_url` puede ser `null` y debe documentarse en la respuesta de la tool.
