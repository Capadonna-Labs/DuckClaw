# Strix Sandbox Security Policy

## Resumen

El sandbox Strix ejecuta codigo dinamico en contenedores Docker con enfoque Zero-Trust:

- red denegada por defecto (`network_mode=none`)
- `cap_drop=ALL` y `no-new-privileges`
- usuario sin privilegios (`1000:1000`)
- montajes de datos en modo solo lectura
- salida en volumen efimero

## Imagen browser (OSINT JobHunter)

Para **`run_browser_sandbox`** (navegación Chromium + Xvfb + browser-use, red según `security_policy.yaml`):

- Imagen por defecto: `duckclaw/browser-env:latest`.
- Variable de entorno: `STRIX_BROWSER_IMAGE` (opcional) para otra etiqueta o registry.
- Build local: `docker build -t duckclaw/browser-env:latest docker/browser-env/`
- La imagen analítica clásica sigue siendo `duckclaw/sandbox:latest` / `STRIX_SANDBOX_IMAGE` para **`run_sandbox`**.

El tiempo máximo de ejecución por corrida toma `max_execution_time_seconds` del YAML (hasta 600s en esquema Pydantic); el proceso hijo se corta por timeout y el contenedor se reinicia en sesiones browser si aplica.

La imagen incluye **noVNC** (websockify en el puerto **6080** dentro del contenedor). Para depuración en máquina de confianza, puedes publicar el puerto con la variable de entorno del **proceso que crea el sandbox** (gateway / graph):

```env
STRIX_BROWSER_PUBLISH_NOVNC=1
```

Luego abre `http://127.0.0.1:6080/vnc.html` en el host. Solo tiene sentido con red tipo `bridge` (p. ej. workers con `network.default: allow` como JobHunter). **No** activar en producción pública: el flujo VNC va sin contraseña pensando en red aislada/ephemeral.

## Politica por worker

Cada worker puede declarar `security_policy.yaml` junto a su `manifest.yaml`.
Si falta el archivo, se aplica una politica estricta por defecto (deny-all).

Ejemplo actual: `forge/templates/finanz/security_policy.yaml`. Perfil browser/OSINT: `forge/templates/job_hunter/security_policy.yaml`.

## Secretos

Solo se inyectan variables listadas en `secrets.allowed_secrets`.
No se escriben secretos en disco y se evita exponerlos en logs.

## Auditoria

Cuando la ejecucion detecta errores de red/permisos (por ejemplo `Read-only file system` o `name resolution`), se registra en `task_audit_log` con estado `SECURITY_VIOLATION_ATTEMPT`.

## Troubleshooting: \"sandbox deshabilitado\" tras `/sandbox on`

El estado `sandbox_enabled` se guarda por **chat_id** en DuckDB. Si en los logs ves:

- `[sandbox-toggle] ... chat_id='1726618406' ...` al activar, pero
- `[sandbox] ... chat_id='default' ... enabled=False` al ejecutar código,

entonces el cliente (p. ej. n8n) está enviando **otro identificador de sesión** en el POST de chat normal, o **no envía** `chat_id` y el gateway usa `default`.

**Qué hacer:** usar el **mismo** id de hilo en todas las peticiones a `/api/v1/agent/chat` (comandos y mensajes).

El gateway resuelve la sesión en este orden:

1. JSON: `chat_id` o alias `session_id`, `thread_id`, `chatId`
2. Query string: `?chat_id=`, `?session_id=`, `?thread_id=`, `?chatId=`
3. Cabeceras: `X-Chat-Id`, `X-Session-Id`, `X-Duckclaw-Chat-Id`

Si no hay ninguno, verás en logs `[session] chat_id ausente en JSON body; usando 'default'`.

## Checklist de validacion manual

Prerequisito: Docker/OrbStack activo en el host.

1) SSRF / exfiltracion bloqueada
- Codigo: `import urllib.request; urllib.request.urlopen("http://google.com")`
- Esperado: fallo de red (name resolution o network unreachable).

2) Aislamiento de host
- Codigo: `print(open('/etc/passwd', 'r').read().splitlines()[0])`
- Esperado: lee el `/etc/passwd` del contenedor, no del host.

3) Bloqueo de escritura en mounts RO
- Codigo: `open('/workspace/data/test.txt', 'w').write('hack')`
- Esperado: `Read-only file system`.

4) Auditoria
- Verificar en `task_audit_log` filas con `status=SECURITY_VIOLATION_ATTEMPT` para los casos 1 y 3.

## Resultados (ejecucion local Strix con `worker_id=finanz`)

- SSRF / exfiltracion (red bloqueada)
  - Codigo: `import urllib.request; urllib.request.urlopen("http://google.com")`
  - Resultado: `exit_code=1` (bloqueo de red; error en stderr)
  - Auditoria: `SECURITY_VIOLATION_ATTEMPT` registrado

- Acceso LFI a host (inofensivo esperado)
  - Codigo: `print(open('/etc/passwd', 'r').read().splitlines()[0])`
  - Resultado: `exit_code=0`
  - Auditoria: no registrado (no es violacion esperada; se lee el `/etc/passwd` del contenedor)

- Bloqueo RO de filesystem
  - Codigo: `open('/workspace/data/test.txt', 'w').write('hack')`
  - Resultado: `exit_code=1` con `OSError: [Errno 30] Read-only file system`
  - Auditoria: `SECURITY_VIOLATION_ATTEMPT` registrado

- Conteo auditoria en `task_audit_log`
  - `SECURITY_VIOLATION_ATTEMPT`: `2`

## Activar OrbStack (Mac) y validar runtime

1) Instalar OrbStack (si no esta instalado)
- GUI: descargar e instalar desde `https://orbstack.dev`.
- CLI (Homebrew):
  - `brew install --cask orbstack`

2) Iniciar OrbStack
- Abrir la app OrbStack desde Applications, o:
  - `open -a OrbStack`
- Esperar a que el daemon de Docker quede `running` en la UI.

3) Verificar que Docker responde
- `docker version`
- `docker info`
- Si ambos comandos responden sin error, el runtime ya esta activo.

4) Verificar desde DuckClaw (Strix)
- `uv run python -c "from duckclaw.graphs.sandbox import _docker_available; print(_docker_available())"`
- Esperado: `True`.

5) Si sigue en `False`
- Reiniciar OrbStack desde UI (Quit + Open).
- Revisar contexto de Docker:
  - `docker context ls`
  - `docker context use default`
- Confirmar que no hay conflicto con otro daemon (Docker Desktop apagado).
- Caso adicional (frecuente): Docker CLI funciona, pero el SDK Python no.
  - Señal: `uv run python -c "from duckclaw.graphs.sandbox import _docker_available; print(_docker_available())"` sigue dando `False`, aunque `docker version`/`docker info` funcionan.
  - Motivo probable: falta el paquete Python `docker` (docker-py) en el entorno, o existe un paquete Python llamado `docker` que no es el SDK.
  - Verifica:
    - `uv run python -c "import docker; print('has_from_env', hasattr(docker,'from_env'))"`
  - Arreglo rápido:
    - `uv pip install docker`
  - Arreglo persistente (recomendado):
    - añadir `docker` como dependency en `packages/agents/pyproject.toml` y ejecutar `uv sync`.

6) Correr validacion de seguridad Strix
- Ejecutar los 3 vectores del checklist anterior (SSRF, RO, /etc/passwd).
- Confirmar auditoria en `task_audit_log`.

