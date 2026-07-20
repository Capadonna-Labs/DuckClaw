# Telegram Gateway — spec mínima

Entrada general: [`docs/README.md`](../../../README.md). Operación: [`docs/COMANDOS.md`](../../../COMANDOS.md) (sección TELEGRAM).

**Dueños de código**

| Área | Ruta |
|------|------|
| Webhook inbound (Update → agent chat) | `services/api-gateway/routers/telegram_inbound_webhook.py` |
| Rutas compactas / multiplex | `services/api-gateway/core/telegram_compact_webhook_routes.py` |
| Auth whitelist | `services/api-gateway/core/chat_auth.py` |
| Salida Bot API / MCP | `services/api-gateway/core/telegram_delivery.py`, `packages/mcp/telegram/` |

Spec relacionada (consola): [`ADMIN_ACCESS_MANAGEMENT.md`](../platform/ADMIN_ACCESS_MANAGEMENT.md) — `authorized_users`, grants compartidos.

---

## Flujo webhook (recomendado)

**Un bot → un proceso gateway → un puerto → una URL HTTPS.**

1. Telegram `POST` Update a `https://<ingress>/api/v1/telegram/webhook`.
2. El gateway valida whitelist (`user_id` / `tenant_id`) y opcionalmente `X-Telegram-Bot-Api-Secret-Token`.
3. El update se encola o invoca el pipeline de agent chat (mismo que `/api/v1/agent/.../chat`).
4. La respuesta sale por Bot API nativa o por MCP Telegram (`TELEGRAM_MCP_ENABLED=1`).

Ingress típico: Tailscale Funnel/Serve, Cloudflare Tunnel o reverse proxy TLS → `127.0.0.1:DUCKCLAW_GATEWAY_PORT`.

```bash
tailscale funnel --bg 8000
uv run duckops ingress telegram-check
uv run duckops ingress telegram-register-webhooks
```

---

## Modo multiplex (opcional)

Varios bots en **un** gateway compartiendo ingress. Variable `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`:

**Formato compacto** (recomendado para registro automático):

```
bot_name:bot_token:/api/v1/telegram/<slug>:worker_id:tenant_id:vault_env_var
```

Entradas separadas por coma. `register_webhooks.py` / `duckops ingress telegram-register-webhooks` lee `DUCKCLAW_PUBLIC_URL` + esta variable.

**Formato JSON** (legacy): lista con `secret`, `worker_id`, `tenant_id`, `bot_token_env`, `vault_db_env`. Si la variable empieza por `[`, se interpreta como JSON.

Cada bot debe usar `secret_token` distinto en `setWebhook` cuando se usa routing por cabecera.

---

## Variables de entorno esenciales

| Variable | Uso |
|----------|-----|
| `TELEGRAM_BOT_TOKEN` o `TELEGRAM_<WORKER>_TOKEN` | Token Bot API del proceso |
| `TELEGRAM_WEBHOOK_SECRET` | `secret_token` de `setWebhook` (modo un bot) |
| `DUCKCLAW_PUBLIC_URL` | Base HTTPS pública (`https://….ts.net`) para registrar webhooks |
| `DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES` | Multiplex compacto o JSON (opcional) |
| `DUCKCLAW_PM2_APP_WORKER_MAP` | `PM2AppName:worker_id` si un gateway sirve un worker por defecto |
| `TELEGRAM_MCP_ENABLED` | `1` para egress vía `duckclaw-telegram-mcp` (`config/mcp_servers.yaml`) |
| `DUCKCLAW_GATEWAY_PORT` / `DUCKCLAW_GATEWAY_URL` | Puerto y URL local del gateway |
| `DUCKDB_PATH` o clave en ruta multiplex | Bóveda DuckDB del bot |

Opcionales: `CHAT_PARALLEL_INVOCATIONS`, `DUCKCLAW_HEARTBEAT_WEBHOOK_URL`, `HEARTBEAT_PLAN_TITLE_INLINE_MAX`.

**Artefactos del sandbox:** el Strix sandbox escribe en `/workspace/output` dentro del contenedor; el host los copia a `output/sandbox/default/` (relativo al CWD del gateway). Ese directorio está gitignored (`output/`) y se recrea en cada ejecución — no versionar. El bot adjunta PNG/Excel/MD desde rutas bajo `output/` cuando la respuesta del agente las cita.

---

## Comandos fly útiles

`/team`, `/team --add <id> [admin]`, `/workers`, `/vault`, `/heartbeat on|off`, `/context on|off`.

Ver [`ADMIN_ACCESS_MANAGEMENT.md`](../platform/ADMIN_ACCESS_MANAGEMENT.md) para whitelist y grants de DB compartida.
