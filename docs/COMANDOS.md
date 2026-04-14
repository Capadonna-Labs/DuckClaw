# COMANDOS — Despliegue rápido DuckClaw

Guía mínima para levantar el entorno desde la **raíz del repositorio** (`duckclaw/`).  
Para contexto y arquitectura, ver **[docs/Installation.md](docs/Installation.md)** (DuckOps Wizard, PM2, seguridad).

---

## 0. Prerrequisitos

- **Node / PM2** (opcional): solo si el wizard registra procesos con PM2.
- **uv**: gestor de dependencias Python del monorepo.
- **Docker** (opcional): forma más simple de correr Redis.

```bash
cd /ruta/al/repo/duckclaw
```

---

## 1. Redis

### Opción A — Docker (recomendada en dev)

```bash
docker run --name redis -d -p 6379:6379 redis
```

Comprobar que responde:

```bash
docker exec -it redis redis-cli ping
```

Debe devolver `PONG`.

Detener o borrar el contenedor cuando no lo necesites:

```bash
docker stop redis
docker rm redis
```

Variables típicas en `.env` (el wizard puede escribirlas):

```env
REDIS_URL=redis://localhost:6379/0
TELEGRAM_BOT_TOKEN=...          # compat: token por defecto si no usas el nombre por agente
TELEGRAM_FINANZ_TOKEN=...       # estándar (id `finanz`); alternativa a TELEGRAM_BOT_TOKEN en gateway Finanz
TELEGRAM_BI_ANALYST_TOKEN=...   # estándar (id `bi_analyst`); antes TELEGRAM_BOT_TOKEN_BI_ANALYST
TELEGRAM_SIATA_ANALYST_TOKEN=... # id `siata_analyst`; antes TELEGRAM_BOT_TOKEN_SIATA
TELEGRAM_LEILAASSISTANT_TOKEN=... # id manifest `LeilaAssistant`; antes TELEGRAM_BOT_TOKEN_LEILA
TELEGRAM_JOB_HUNTER_TOKEN=...   # id `Job-Hunter` / JobHunter-Gateway (según config PM2)
# Opcional legado: N8N_OUTBOUND_WEBHOOK_URL + DUCKCLAW_TELEGRAM_OUTBOUND_VIA=n8n
```

Los logs PM2 muestran rutas `telegram native ...` / `outbound deliver ...` a nivel INFO cuando el gateway envía mensajes.

---

## 2. Webhook nativo Telegram (ingress)

Puedes recibir mensajes del bot **sin n8n**: Telegram hace `POST` al API Gateway con el objeto [Update](https://core.telegram.org/bots/api#update).

| Concepto | Detalle |
|---------|---------|
| Ruta | `POST https://<tu-host>/api/v1/telegram/webhook` (HTTPS público obligatorio para producción) |
| Seguridad | Con `TELEGRAM_WEBHOOK_SECRET` en el entorno del gateway, Telegram debe enviar el **mismo** valor como `secret_token` en `setWebhook`; llega en la cabecera `X-Telegram-Bot-Api-Secret-Token`. Si el secreto está vacío, el endpoint acepta updates sin cabecera (solo desarrollo). |
| Tailscale | Esta ruta **no** exige `X-Tailscale-Auth-Key` (Telegram no puede enviarla). |
| Un bot, un webhook | Antes de apuntar Telegram a DuckClaw, **desactiva** el *Telegram Trigger* de n8n (u otro servicio) para ese bot; si no, los mensajes seguirán yendo al webhook anterior. |
| Redis | Opcional pero recomendado: deduplica por `update_id` (evita doble procesamiento en reintentos de Telegram). |

### 2.0 Un gateway PM2, un webhook HTTPS (recomendado)

Cada proceso gateway es el mismo código pero con **env y puerto distintos** ([`config/api_gateways_pm2.json`](config/api_gateways_pm2.json): p. ej. Finanz-Gateway `8000`, JobHunter-Gateway `8283`, BI-Analyst-Gateway `8282`). Telegram solo llama la URL que configures en `setWebhook`; si un único `tailscale funnel --yes <puerto>` apunta solo al JobHunter, **todos** los bots que compartan esa URL entrarán por ese proceso (mal para logs y para ACL). El modelo recomendado:

1. Cada bot tiene una URL HTTPS cuya **terminación** llega al **puerto de ese** PM2 (verifica con `pm2 describe <nombre>` / JSON de puertos).
2. Usa siempre el path estándar `…/api/v1/telegram/webhook` y el `secret_token` del **mismo** proceso.

**Ingress:** elige cómo mapear Internet → `127.0.0.1:<puerto>` (al menos una línea por gateway o un proxy que enrute):

| Enfoque | Cuándo usarlo |
|--------|----------------|
| **Túnel / hostname por servicio** | P. ej. Cloudflare Tunnel: dos `public_hostnames` → `http://127.0.0.1:8000` y `http://127.0.0.1:8283`. Cada bot `setWebhook` apunta al hostname que toca. |
| **Tailscale Funnel** | Un comando `tailscale funnel --bg --yes <puerto>` expone **un** puerto por máquina en la URL `ts.net` habitual; **volver a ejecutarlo con otro puerto reemplaza el destino** de esa misma URL pública. Por eso, si el Sovereign Wizard activa Funnel primero para Finanz (`8000`) y luego para SIATA (`8888`), **todos** los bots cuyo `setWebhook` siga apuntando a `https://nodo….ts.net/...` recibirán updates en **8888** — no es que PM2 o `.env` sobrescriban tokens, es el túnel. Para varios gateways: varios hostnames/túneles, proxy con virtual hosts, **Tailscale Serve** con reglas por ruta/host ([KB Funnel](https://tailscale.com/kb/1223/funnel/)), o multiplexación (§2.0 Modo B). El wizard muestra un aviso amarillo si detecta cambio de puerto. |
| **Reverse proxy local (Caddy/nginx)** | Un frontal TLS en `443` que enruta por host o path a `8000` / `828x`; un solo funnel al `443` del proxy. |

Especificación: [specs/features/Telegram Webhook One Gateway One Port.md](specs/features/Telegram%20Webhook%20One%20Gateway%20One%20Port.md).

**Registrar el webhook** (sustituye `TOKEN`, URL pública que llega **a ese** puerto y `TELEGRAM_WEBHOOK_SECRET` del env de **ese** proceso):

```bash
curl -sS -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://tu-dominio.example/api/v1/telegram/webhook",
    "secret_token": "<TELEGRAM_WEBHOOK_SECRET>",
    "allowed_updates": ["message", "edited_message"]
  }'
```

Ejemplo alineado al JSON de gateways (ajusta el host al túnel/proxy real):

- Bot Finanz (`TELEGRAM_FINANZ_TOKEN`): `url` debe terminar en el proceso que escucha el puerto **8000** (p. ej. `https://finanz.tu-tunnel.example/api/v1/telegram/webhook`).
- Bot Job Hunter (`TELEGRAM_JOB_HUNTER_TOKEN` / `TELEGRAM_BOT_TOKEN` en ese PM2): `url` debe terminar en el puerto del **JobHunter-Gateway** (p. ej. **8283** en el repo, o el que tengas en PM2).

Comprobar estado:

```bash
curl -sS "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Quitar webhook (p. ej. antes de cambiar de proveedor):

```bash
curl -sS -X POST "https://api.telegram.org/bot<TOKEN>/deleteWebhook"
```

**Enrutado al grafo** (variables de entorno del proceso PM2): worker efectivo  
`DUCKCLAW_TELEGRAM_DEFAULT_WORKER` → `DUCKCLAW_DEFAULT_WORKER_ID` → `finanz`; tenant en el body interno  
`DUCKCLAW_TELEGRAM_DEFAULT_TENANT` → `DUCKCLAW_GATEWAY_TENANT_ID` → `default`.  
`_invoke_chat` sigue aplicando la misma normalización de tenant que `POST /api/v1/agent/chat`.

**Modo B — Varios bots → misma URL pública (un solo Funnel/puerto):** cuando Tailscale Funnel (u otro túnel) solo puede llegar a **un** puerto local, deja ese puerto como **único** receptor de Telegram (p. ej. tu funnel a `127.0.0.1:8888` → proceso **SIATA-Gateway**). Los otros gateways PM2 pueden seguir levantados para HTTP interno, pero **no** recibirán el webhook a menos que montes otro túnel.

1. En el bloque `env` del proceso que recibe el funnel, define **todos** los tokens y rutas DuckDB que necesiten los bots (p. ej. `TELEGRAM_FINANZ_TOKEN`, `DUCKCLAW_FINANZ_DB_PATH`, `TELEGRAM_JOB_HUNTER_TOKEN`, `DUCKCLAW_JOB_HUNTER_DB_PATH`; el propio proceso ya tiene `TELEGRAM_SIATA_TOKEN` y `DUCKCLAW_DB_PATH` para SIATA).
2. Variable `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`: JSON **array**; cada elemento tiene `secret` (mismo string que `secret_token` en `setWebhook` de **ese** bot), `worker_id`, `tenant_id` (opcional), `bot_token_env`, y **`vault_db_env`** (opcional pero recomendado): nombre de variable cuyo valor es la DuckDB de ese bot — sin eso, el grafo usaría el `DUCKCLAW_DB_PATH` del PM2 equivocado.

Ejemplo (genera tres secretos distintos, p. ej. `openssl rand -hex 32`, y úsalos en `setWebhook` y en `secret`):

```json
[
  {"secret":"SEC_FINANZ","worker_id":"finanz","tenant_id":"Finanzas","bot_token_env":"TELEGRAM_FINANZ_TOKEN","vault_db_env":"DUCKCLAW_FINANZ_DB_PATH"},
  {"secret":"SEC_SIATA","worker_id":"siata_analyst","tenant_id":"SIATA","bot_token_env":"TELEGRAM_SIATA_TOKEN","vault_db_env":"DUCKCLAW_DB_PATH"},
  {"secret":"SEC_TRABAJO","worker_id":"Job-Hunter","tenant_id":"Trabajo","bot_token_env":"TELEGRAM_JOB_HUNTER_TOKEN","vault_db_env":"DUCKCLAW_JOB_HUNTER_DB_PATH"}
]
```

En PM2, `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES` debe ser **una sola línea** JSON escapada o definida en `ecosystem` como string. Cada bot: misma `url` (`https://tu-nodo.ts.net/api/v1/telegram/webhook`), **`secret_token` distinto** por bot.

Si además tienes `TELEGRAM_WEBHOOK_SECRET`, solo los updates cuya cabecera coincida con ese valor usarán el “default” del proceso (worker/tenant/token del PM2); el resto debe coincidir con una entrada de `ROUTES`. Especificación: [specs/features/Telegram Webhook Multiplex (multi-bot).md](specs/features/Telegram%20Webhook%20Multiplex%20(multi-bot).md). Rutas `POST …/webhook/finanz` y `…/webhook/trabajo` son **legado**; con un solo funnel suele bastar Modo B + `vault_db_env`.

**Modo compacto (path por bot, misma base `DUCKCLAW_PUBLIC_URL`):** si `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES` **no** empieza por `[` y contiene `:/api/`, se interpreta como lista separada por comas `bot_name:bot_token:webhook_path`. El gateway crea `POST` bajo `/api/v1/telegram/...` (p. ej. `/finanz`). Perfiles admitidos: `finanz`, `siata`, `jobhunter`. Define las mismas variables de DuckDB que en modo multi-puerto (`DUCKCLAW_FINANZ_DB_PATH`, `DUCKCLAW_JOB_HUNTER_DB_PATH`, `DUCKCLAW_SIATA_DB_PATH` o `DUCKCLAW_DB_PATH`). **Obligatorio:** tras definir la variable, ejecuta `python scripts/register_webhooks.py` (con `DUCKCLAW_PUBLIC_URL` y tokens en la cadena). Si los bots siguen con `setWebhook` en `…/api/v1/telegram/webhook`, todos los updates caen en esa ruta y el gateway **no** puede saber qué bot es: en ese modo, el gateway ignora el POST genérico y solo procesa los paths dedicados (`…/finanz`, `…/siata`, …). Opcional: `TELEGRAM_WEBHOOK_SECRET` como `secret_token` común en el script.

**Prueba local** del router (Telegram no llama a HTTP sin TLS; sirve para depurar en la máquina):

```bash
curl -sS -X POST http://127.0.0.1:8282/api/v1/telegram/webhook \
  -H "Content-Type: application/json" \
  -H "X-Telegram-Bot-Api-Secret-Token: <opcional_si_TELEGRAM_WEBHOOK_SECRET_está_definido>" \
  -d '{"update_id":1,"message":{"message_id":1,"chat":{"id":123456789,"type":"private"},"from":{"id":123456789,"is_bot":false,"first_name":"Test"},"text":"hola"}}'
```

Más contexto: [specs/features/Migracion de Orquestacion n8n a Integracion Nativa Telegram.md](specs/features/Migracion%20de%20Orquestacion%20n8n%20a%20Integracion%20Nativa%20Telegram.md).

### 2.1 Paralelismo por chat y etiquetas «BI-Analyst N»

Por defecto el gateway **serializa** las invocaciones al grafo por `chat_id` (un mensaje en curso por conversación). Para permitir varias peticiones concurrentes en el mismo chat (p. ej. tres preguntas seguidas en Telegram antes de que termine la primera):

```env
DUCKCLAW_CHAT_PARALLEL_INVOCATIONS=1
```

Valores reconocidos: `1`, `true`, `yes`, `on` (insensible a mayúsculas). Debe estar definida en el **mismo** proceso que ejecuta el gateway **y** el que carga el grafo (PM2 / `.env` del `BI-Analyst-Gateway` u otro gateway que use `graph_server` con ese entorno).

| Aspecto | Con paralelismo activado |
|--------|---------------------------|
| Webhook | Responde `200` enseguida; el grafo sigue en segundo plano (`asyncio.create_task`). |
| Riesgos | Historial Redis, `/tasks` y el orden de llegada de respuestas en Telegram pueden **intercalarse**; activar solo si lo necesitas. |
| Etiquetas | `BI-Analyst 1`, `BI-Analyst 2`, … indican el **número de instancia entre ejecuciones activas** del mismo worker en **ese** chat (ocupación de slot), no un contador monotónico por turno. Si solo queda una corrida, vuelve a ser `1`. |
| Redis | Recomendado: los slots viven en claves `duckclaw:subagent_active:{tenant}:{worker}:{chat}` (ZSET); sin Redis coherente entre workers, el fallback en memoria solo vale para un solo proceso. |

Heartbeats de delegación (mensajes «paso actual») pueden incluir el título del plan; límite de caracteres del título en línea:

```env
DUCKCLAW_HEARTBEAT_PLAN_TITLE_INLINE_MAX=90
```

Si la variable está vacía o no es un entero válido, se usa el valor por defecto del código (no dejes la variable vacía a propósito).

### 2.2 Pool de lectura DuckDB (varias `read_sql` / `inspect_schema` en un turno)

Cuando el modelo devuelve **varias** tool calls de solo lectura en el mismo mensaje, el worker puede ejecutarlas **en paralelo** sobre conexiones DuckDB **efímeras `read_only`** (no comparten la conexión interna de `DuckClaw`). Solo aplica si **todas** las herramientas del turno son `read_sql` y/o `inspect_schema`; si en el mismo turno aparece sandbox, `admin_sql`, etc., se vuelve al modo secuencial.

Variables de entorno (proceso que ejecuta el grafo del worker, p. ej. PM2 del gateway):

```env
DUCKCLAW_TOOL_READ_POOL_ENABLED=1          # default activo; 0/false/no/off desactiva
DUCKCLAW_TOOL_READ_POOL_CONCURRENCY=5    # máximo de lecturas efímeras concurrentes
DUCKCLAW_TOOL_READ_STMT_TIMEOUT_MS=10000 # timeout de sentencia en ms (DuckDB SET statement_timeout)
DUCKCLAW_TOOL_READ_POOL_RETRIES=3        # reintentos ante lock/IO transitorio
```

Límite de tamaño de respuesta SQL hacia el LLM (también en el camino efímero):

```env
DUCKCLAW_READ_SQL_MAX_RESPONSE_CHARS=80000
```

Por **worker**, en `manifest.yaml`:

```yaml
tool_read_pool: false   # desactiva el pool para ese template (pese al default global)
```

Especificación: [specs/features/Concurrent Tool Node (Ephemeral Read-Pool).md](specs/features/Concurrent%20Tool%20Node%20(Ephemeral%20Read-Pool).md).

### 2.3 Context injection (Telegram `/context`)

Comandos del **webhook nativo** para memoria semántica en la bóveda DuckDB del usuario (`main.semantic_memory`). Detalle: [specs/features/Context Injection (Telegram).md](specs/features/Context%20Injection%20(Telegram).md).

| Comando | Efecto |
|---------|--------|
| `/context --add <texto>` | Solo **admin** (mismo RBAC que Telegram Guard: `main.authorized_users`, War Room, o owner). Encola un `STATE_DELTA` en Redis → **DuckClaw-DB-Writer** inserta chunks en `main.semantic_memory`. Respuesta inmediata de acuse; el **resumen** se genera en segundo plano con `[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]` (no bloquea el webhook). Sufijo de bot: `/context@MiBot --add …`. |
| `/context --summary` | Alias: `--summarize`, `--peek`, `--db`. **Solo lectura** de filas recientes en `main.semantic_memory` (sin `LPUSH`). Acuse + resumen en segundo plano con `[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]`. Si no hay datos, mensaje fijo **sin** LLM. |

**Requisitos para `--add`:** `REDIS_URL` y proceso **DuckClaw-DB-Writer** activo (cola por defecto `duckclaw:state_delta:context`). Sin writer, el acuse puede mostrarse pero la persistencia queda pendiente en Redis.

**Variable de cola:** `DUCKCLAW_CONTEXT_STATE_DELTA_QUEUE` (sobrescribe el nombre de la lista Redis anterior).

**Locks DuckDB (gateway RO vs writer RW):** Tras un `--add`, el gateway puede abrir la bóveda en solo lectura con reintentos. Opcional: `DUCKCLAW_GATEWAY_RO_LOCK_ATTEMPTS` (default `24`) y `DUCKCLAW_GATEWAY_RO_LOCK_BASE_SLEEP_S` (default `0.15`).

---

## 3. Dependencias Python del monorepo

```bash
uv sync
```

Con extra Telegram (bot por long polling), si lo necesitas:

```bash
uv sync --extra telegram
```

El **API Gateway** (Python 3.10+) arranca un cliente MCP hijo si activas el flag (PM2 o `.env`):

```env
DUCKCLAW_TELEGRAM_MCP_ENABLED=1
TELEGRAM_BOT_TOKEN=...
```

Opcional: `enabled: true` en `config/mcp_servers.yaml` bajo `mcp_servers.telegram`. Con la sesión activa, el egress de respuestas largas y fotos sandbox usa `telegram_send_*` vía MCP; si falla, Bot API directa. Los webhooks n8n de salida solo se usan si `DUCKCLAW_TELEGRAM_OUTBOUND_VIA=n8n`.

**Probar MCP → Telegram (stdio, sin gateway):** desde la raíz, con `TELEGRAM_BOT_TOKEN` en `.env` o en el entorno y tu `chat_id` (el mismo que usa el bot):

```bash
uv run python scripts/smoke_telegram_mcp_stdio.py TU_CHAT_ID
```

Deberías ver `tools MCP: [...]` y un JSON con `ok: true` y `message_id` si Telegram aceptó el mensaje. Los logs del proceso hijo van por stderr (`duckclaw.telegram_mcp`).

### Reddit MCP (Finanz / sentimiento social)

El worker **Finanz** puede cargar herramientas Reddit vía **stdio** (`npx --quiet -y mcp-reddit`) cuando el manifest incluye un bloque `reddit:` (ver template [packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml](packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml)).

**Requisitos:** Node.js y `npx` en el `PATH` del proceso del API Gateway (igual que GitHub MCP). Variables en el entorno del gateway (no commitear secretos):

```env
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=app:version (by /u/tu_usuario)
REDDIT_USERNAME=...
REDDIT_PASSWORD=...
```

Crea la app en [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) (tipo script). Spec: [specs/features/Reddit MCP Social Sentiment (QuantClaw).md](specs/features/Reddit%20MCP%20Social%20Sentiment%20(QuantClaw).md).

Tras cambiar `.env`, reinicia el gateway (PM2). Por defecto `read_only: true` solo registra búsqueda y lectura de posts/comentarios.

### Google Trends MCP (Finanz / interés macro)

Instala el paquete del servidor (pytrends, sin API key obligatoria):

```bash
uv sync --extra google-trends
```

El proceso hijo usa el ejecutable **`google-trends-mcp`** del mismo entorno que el gateway (o `uvx google-trends-mcp` si no está en el venv). Bloque en manifest: `google_trends:` — ver [packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml](packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml).

Opcionalmente puedes fijar `command` y `args` en YAML para otro lanzador. Limitaciones: acceso no oficial a Google Trends; posibles bloqueos o errores intermitentes. Spec: [specs/features/Google Trends MCP (Macro Interest Finanz).md](specs/features/Google%20Trends%20MCP%20(Macro%20Interest%20Finanz).md).

### Cyber-Fluid Dynamics (Finanz / quant)

Con `quant.cfd: true` en el manifest del template Finanz se registra la herramienta `record_fluid_state` y la tabla `quant_core.fluid_state` (OHLCV + métricas heurísticas y fase SOLID|LIQUID|GAS|PLASMA). Ver spec [specs/features/Cyber-Fluid Dynamics CFD (Finanz).md](specs/features/Cyber-Fluid%20Dynamics%20CFD%20(Finanz).md). Tras aplicar `schema.sql` nuevo, reinicia el gateway si hace falta recrear el grafo.

---

## 4. Wizard — aprovisionamiento interactivo

**`duckops init`** ejecuta por defecto el **Sovereign Wizard v2.0** (TUI con `prompt_toolkit`, borrador en memoria y escritura solo tras confirmar en *Review*; atajos Ctrl+Z/Esc, Ctrl+S, Ctrl+R, Tab). Tras **CONFIRMAR**, materializa `.env`, rutas DuckDB, PM2 según el borrador y puede registrar `setWebhook`. Opcional: `--repo` / `-C` para la raíz del monorepo. Spec: [specs/features/DuckClaw Sovereign Wizard (v2.0).md](specs/features/DuckClaw%20Sovereign%20Wizard%20(v2.0).md).

```bash
uv run duckops init
uv run duckops init --repo /ruta/al/duckclaw
```

Wizard **clásico** (Rich, `scripts/duckclaw_setup_wizard.py`): `uv run duckops init --classic`.

Borrador rápido (sin tocar el `.env` del repo): **Ctrl+S** → `~/.config/duckclaw/wizard_draft.json`.

Detalle de fases y seguridad: [docs/Installation.md](docs/Installation.md).

---

## 5. API Gateway (desarrollo)

Desde la raíz del repo:

```bash
uv run duckops serve --gateway
```

Equivalente orientativo (si prefieres llamar uvicorn a mano; ajusta host/puerto):

```bash
cd services/api-gateway
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Comprobación rápida:

```bash
curl -s http://127.0.0.1:8000/health
```

(Si usas `DUCKCLAW_TAILSCALE_AUTH_KEY`, añade la cabecera `X-Tailscale-Auth-Key` en las peticiones, salvo rutas públicas documentadas.)

### 5.1 Finanz + análisis cuantitativo (IBKR / quant_core)

Implementación acoplada al template [finanz](packages/agents/src/duckclaw/forge/templates/finanz/manifest.yaml) (spec: [Quantitative Trading Worker](specs/features/Quantitative%20Trading%20Worker.md); lake + SSH: [Capadonna Lake OHLC SSH + IBKR Live](specs/features/Capadonna%20Lake%20OHLC%20SSH%20+%20IBKR%20Live.md)).

| Variable | Uso |
|----------|-----|
| `IBKR_PORTFOLIO_API_URL` / `IBKR_PORTFOLIO_API_KEY` | Resumen de portafolio (`get_ibkr_portfolio`). Las peticiones envían la cabecera `X-Duckclaw-IBKR-Account-Mode` según `IBKR_ACCOUNT_MODE` (default `paper`) para que tu API enrute al Gateway paper/live. |
| `IBKR_MARKET_DATA_URL` | **Solo la URL base** del endpoint (sin query), p. ej. `http://100.x.x.x:8002/api/market/ohlcv`. El cliente añade `?ticker=&timeframe=&lookback_days=`. En el VPS, el mismo path puede usar **lake** (`export_lake_ohlcv.py`) y, si no hay barras, **fallback IB** (`scripts/capadonna/ibkr_historical_bars.py`, `ib_async` + `OHLCV_IB_*`; ver spec). Contrato: [Capadonna Lake + IBKR Live](../specs/features/Capadonna%20Lake%20OHLC%20SSH%20+%20IBKR%20Live.md). Referencia: [services/ibkr-ohlcv-api](../services/ibkr-ohlcv-api/main.py). Si no existe esa ruta (404), déjala **vacía**: el lake histórico sigue por SSH. |
| `IBKR_MARKET_DATA_API_KEY` | Opcional; Bearer para OHLCV. Si no se define, `fetch_market_data` usa `IBKR_PORTFOLIO_API_KEY`. |
| `IBKR_REALTIME_TIMEFRAMES` | CSV de timeframes que van al gateway HTTP cuando **no** están solo en rama lake (default `1m,5m,15m,30m,1h`). Si un TF está en histórico lake **y** aquí, prevalece IBKR. Añade `1d` si el lake SSH falla y quieres diario por HTTP. |
| `CAPADONNA_SSH_HOST` | IP/host Tailscale del VPS con el data lake (histórico). |
| `CAPADONNA_SSH_USER` | Usuario SSH (default `capadonna`). |
| `CAPADONNA_SSH_KEY_PATH` | Preferente; ruta local a clave privada (`-i`), p. ej. `~/.ssh/id_ed25519`. Si no se define, se usa `CAPADONNA_SSH_IDENTITY_FILE`. |
| `CAPADONNA_SSH_IDENTITY_FILE` | Alias histórico; `-i` si `CAPADONNA_SSH_KEY_PATH` está vacío. |
| `CAPADONNA_SSH_TIMEOUT` | Segundos (default `120`, máx. `600`). |
| `CAPADONNA_REMOTE_OHLC_CMD` | Plantilla ejecutada **en el VPS por ssh** (usa rutas absolutas del servidor, p. ej. `/home/capadonna/...`, no `~` de tu Mac). Intérprete: venv del proyecto Capadonna-Driller (`…/.venv/bin/python`) con `duckdb` instalado. Script: `scripts/capadonna/export_lake_ohlcv.py`. Opcional `CAPADONNA_LAKE_DATA_ROOT`. |
| `CAPADONNA_HISTORICAL_TIMEFRAMES` | CSV de timeframes que van al lake por SSH (default en código `1d,1w,1M,moc`). Incluye `moc` para `data/lake/moc/`. **Mes = `1M` mayúscula; minuto = `1m` minúscula** (el bridge no las mezcla). Requiere host + comando remoto. |
| `IBKR_ACCOUNT_MODE` | Debe ser `paper` para permitir `execute_order` / `execute_approved_signal`. |
| `IBKR_EXECUTE_ORDER_URL` | POST JSON `{"signal_id","paper":true}` (opcional; sin URL la orden no se envía al broker tras HITL). El **time-in-force** (GTC, bracket, etc.) lo define tu servicio detrás de esta URL, no el monorepo. |
| `DUCKCLAW_QUANT_HITL_GRANT_TTL_SEC` | Segundos de validez del grant tras `/execute_signal` (default `600`). Para swing o confirmacion lenta, sube (p. ej. `86400`). |
| `REDIS_URL` / `DUCKCLAW_REDIS_URL` | Recomendado para persistir grants de `/execute_signal` entre procesos; si falta, memoria en proceso (solo mismo worker). |

Ejemplo de bloque (proceso del gateway; no commitear valores reales):

```bash
# Capadonna Lake (histórico SSH, típ. Tailscale)
CAPADONNA_SSH_HOST=100.x.x.x
CAPADONNA_SSH_USER=capadonna
CAPADONNA_SSH_KEY_PATH=~/.ssh/id_ed25519
# En el VPS: /home/capadonna/projects/Capadonna-Driller/.venv/bin/pip install duckdb
CAPADONNA_REMOTE_OHLC_CMD=/home/capadonna/projects/Capadonna-Driller/.venv/bin/python /home/capadonna/projects/Capadonna-Driller/scripts/export_lake_ohlcv.py {ticker} {timeframe} {lookback_days}
CAPADONNA_HISTORICAL_TIMEFRAMES=1d,1w,1M,moc
```

Fly: `/lake` o `/lake status` comprueba env y hace `ssh … true` corto si la config es válida. `/sensors` resume DuckDB, IBKR (portafolio + mercado), Lake, Tavily, Reddit, Google Trends y **browser sandbox** (manifest finanz, Docker, imagen Playwright, red en `security_policy`) en el proceso del gateway.

Telegram (human-in-the-loop): el usuario confirma con `/execute_signal <uuid>` el `signal_id` devuelto por la propuesta (`propose_trade` en **Finanz**, `propose_trade_signal` en **Quant Trader**). Luego el asistente llama `execute_order` (Finanz) o `execute_approved_signal` (Quant Trader).

---

## 6. DB Writer (si usas escrituras encoladas)

El wizard soberano puede generar `ecosystem.db-writer.config.cjs` en la **raíz del repo**. Además de la cola SQL (`duckdb_write_queue`), el proceso escucha **CONTEXT_INJECTION** (`duckclaw:state_delta:context` por defecto) para persistir `/context --add` en `main.semantic_memory`.

**PM2** (recomendado en servidor; nombre del proceso: `DuckClaw-DB-Writer`):

```bash
# Desde la raíz del monorepo
pm2 start ecosystem.db-writer.config.cjs
# Si el archivo define más de una app y solo quieres el writer:
pm2 start ecosystem.db-writer.config.cjs --only DuckClaw-DB-Writer
pm2 save   # opcional: persistir la lista de procesos PM2

# Tras cambiar REDIS_URL, DUCKDB_PATH o rutas multiplex en ese ecosystem:
pm2 restart DuckClaw-DB-Writer --update-env
pm2 logs DuckClaw-DB-Writer
```

El bloque `env` del ecosystem debe llevar la misma **`REDIS_URL`** (o `DUCKCLAW_REDIS_URL`) que el gateway y un **`DUCKDB_PATH`** coherente con la bóveda donde quieres aplicar las escrituras encoladas (alineado con multiplex / hub del gateway).

**Manual** (desarrollo u one-off):

```bash
uv run python services/db-writer/main.py
```

### Depuración Telegram `/team` (whitelist)

Si `/team --add` responde bien pero `/team` lista vacío: define `DUCKCLAW_TEAM_WHITELIST_DEBUG=1`, reinicia el gateway (PM2) y busca en logs `fly_team_audit` y mensajes del logger `duckclaw.team_whitelist` (comparan bóveda fly vs hub y la rama `reuse_fly`).

Consulta directa en la `.duckdb` del hub:

```bash
uv run python scripts/check_authorized_users.py --db db/private/TU_USER/finanzdb1.duckdb --tenant Finanzas
```

Sin `--db` usa `get_gateway_db_path()` según el `.env` / multiplex actual.

---

## 7. Orden sugerido (resumen)

| Paso | Comando |
|------|---------|
| 1 | `docker run --name redis -d -p 6379:6379 redis` **o** `redis-server` |
| 2 | `redis-cli ping` → `PONG` |
| 3 | `uv sync` |
| 4 | `uv run duckops init` |
| 5 | `uv run duckops serve --gateway` |
| 6 | (Opcional Telegram) `DUCKCLAW_CHAT_PARALLEL_INVOCATIONS=1` + `REDIS_URL` para varias respuestas concurrentes por chat; **§2.2** `DUCKCLAW_TOOL_READ_POOL_*` si varias `read_sql` en un solo turno; reiniciar con `--update-env` |
| 7 | (Opcional) DB Writer: **§6** (`pm2 start ecosystem.db-writer.config.cjs` o `uv run python services/db-writer/main.py`) — **necesario** para `/context --add` (§2.3) |

---

## 8. Cheat sheet del día a día

```bash
uv run duckops init                         # Reconfigurar / instalar
uv run duckops serve --gateway              # Solo gateway en dev
pm2 status                                  # Si usas PM2 tras el wizard
pm2 logs BI-Analyst-Gateway                 # Ej.: traza Telegram + subagentes
pm2 logs JobHunter-Gateway                  # Job-Hunter + resúmenes /context
pm2 logs DuckClaw-DB-Writer                 # Escrituras + CONTEXT_INJECTION
pm2 flush                                   # Vaciar logs PM2
pm2 restart BI-Analyst-Gateway --update-env # Nombre según config/api_gateways_pm2.json; tras cambiar DUCKCLAW_*
# Tras cambiar DUCKCLAW_TOOL_READ_POOL_* o DUCKCLAW_READ_SQL_MAX_RESPONSE_CHARS: mismo restart
# Telegram (admin): /context --add …  |  /context --summary  — ver §2.3
```

Más comandos: sección **6. Guía Rápida de Operación** en [docs/Installation.md](docs/Installation.md).
