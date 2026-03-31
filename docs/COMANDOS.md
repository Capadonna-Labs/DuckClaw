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

### Opción B — Redis instalado en el sistema

Si ya tienes `redis-server` en el PATH:

```bash
redis-server
```

(En otra terminal) verificación:

```bash
redis-cli ping
```

Variables típicas en `.env` (el wizard puede escribirlas):

```env
REDIS_URL=redis://localhost:6379/0
TELEGRAM_BOT_TOKEN=...          # salida a Telegram vía Bot API (recomendado; sin n8n)
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

Expose el puerto del proceso correcto detrás de HTTPS (Cloudflare Tunnel, Tailscale Funnel, reverse proxy, etc.). Ejemplo BI Analyst: gateway en `8282` según [config/api_gateways_pm2.json](config/api_gateways_pm2.json).

**Registrar el webhook** (sustituye `TOKEN`, URL y secreto; el secreto debe coincidir con `TELEGRAM_WEBHOOK_SECRET`):

```bash
curl -sS -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://tu-dominio.example/api/v1/telegram/webhook",
    "secret_token": "<TELEGRAM_WEBHOOK_SECRET>",
    "allowed_updates": ["message", "edited_message"]
  }'
```

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

---

## 4. Wizard — aprovisionamiento interactivo

Inicializa `.env`, rutas de DuckDB, PM2/systemd según el flujo del proyecto:

```bash
uv run duckops init
```

**Sovereign Wizard v2.0** (TUI con `prompt_toolkit`, borrador en memoria y escritura solo tras confirmar en *Review*; atajos Ctrl+Z/Esc, Ctrl+S, Ctrl+R, Tab). Spec: [specs/features/DuckClaw Sovereign Wizard (v2.0).md](specs/features/DuckClaw%20Sovereign%20Wizard%20(v2.0).md).

```bash
uv run duckops sovereign
# equivalente:
uv run duckops init --sovereign
```

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

---

## 6. DB Writer (si usas escrituras encoladas)

El wizard puede registrarlo en PM2. Arranque manual orientativo:

```bash
uv run python services/db-writer/main.py
```

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
| 7 | (Opcional) `uv run python services/db-writer/main.py` o PM2 según [Installation.md](docs/Installation.md) |

---

## 8. Cheat sheet del día a día

```bash
uv run duckops init                         # Reconfigurar / instalar
uv run duckops serve --gateway              # Solo gateway en dev
pm2 status                                  # Si usas PM2 tras el wizard
pm2 logs BI-Analyst-Gateway                 # Ej.: traza Telegram + subagentes
pm2 logs DuckClaw-DB-Writer                 # Auditar escrituras
pm2 flush                                   # Vaciar logs PM2
pm2 restart BI-Analyst-Gateway --update-env # Nombre según config/api_gateways_pm2.json; tras cambiar DUCKCLAW_*
# Tras cambiar DUCKCLAW_TOOL_READ_POOL_* o DUCKCLAW_READ_SQL_MAX_RESPONSE_CHARS: mismo restart
```

Más comandos: sección **6. Guía Rápida de Operación** en [docs/Installation.md](docs/Installation.md).
