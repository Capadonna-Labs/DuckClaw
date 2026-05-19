# Gateway canales agnósticos (Telegram, Discord, extensión)

## Objetivo

Unificar la **entrada** (webhooks / eventos) y la **salida** (entrega de respuestas) del API Gateway en torno a un contrato común, sin duplicar el orquestador de agente (`_invoke_chat`, MLX, db-writer singleton). Hoy: **Telegram** y **Discord**; mañana: **Slack**, **Gmail** (batch), u otros con el mismo patrón de adaptador.

## Contrato `chat_id` / `session_id` (URN)

- **Recomendado** (modo explícito vía `DUCKCLAW_CHANNEL_URN_SESSIONS=1`):
  - Telegram: `telegram:<telegram_chat_id>`
  - Discord: `discord:<guild_snowflake>:<channel_snowflake>:<user_snowflake>`
- **Compatibilidad (default `0`):** Telegram sigue usando el **ID numérico plano** como hasta ahora; Discord usa URN o string opaco estable definido por el adaptador.

Historial Redis y locks usan el mismo `session_id` que recibe el gateway; si el URN supera límites de clave, documentar hash estable (futuro).

## Idempotencia

- Telegram: claves existentes `duckclaw:dedupe:telegram:webhook:update` (sin cambio de semántica).
- Discord: dedupe por `interaction_id` (snowflake único por interacción) en prefijo `duckclaw:dedupe:discord:interaction` con TTL breve (p. ej. 300s).

## Routing unificado (`DUCKCLAW_CHANNEL_ROUTES`)

Variable opcional (JSON array). Cada elemento:

| Campo | Descripción |
|-------|-------------|
| `channel` | `discord` \| `slack` (futuro) |
| `match` | Objeto discriminador, p. ej. `{"guild_id": "..."}` |
| `worker_id` | Worker LangGraph (ej. `quant_trader`) |
| `tenant_id` | Tenant efectivo |
| `bot_token_env` | Nombre de variable de entorno con **token del bot** Discord (no loguear valor) |
| `vault_db_env` | Opcional: env con ruta `.duckdb` forzada (análogo a multiplex Telegram) |

Si la variable está vacía, Discord puede resolverse solo con `DUCKCLAW_DISCORD_PUBLIC_KEY` + token vía `DUCKCLAW_DISCORD_BOT_TOKEN` (un solo bot).

## Autenticación Discord (Interactions)

- Verificación **ed25519** del cuerpo crudo con cabeceras `X-Signature-Ed25519` y `X-Signature-Timestamp` y `DISCORD_PUBLIC_KEY` / `DUCKCLAW_DISCORD_PUBLIC_KEY`.
- **PING** (`type == 1`): responder `{"type": 1}` inmediato.
- **Comando `/duckclaw` (MVP):** responder `type: 5` (DEFERRED) dentro del presupuesto de latencia; luego **PATCH** `webhooks/{application_id}/{interaction_token}/messages/@original` con el texto de respuesta (troceado a 2000 caracteres).

## Outbound por canal

| Canal | Mecanismo MVP |
|-------|----------------|
| Telegram | MCP opcional, Bot API nativa, Telegram webhook inbound (`POST /api/v1/telegram/webhook`) |
| Discord | REST Bot API (PATCH follow-up tras defer) |
| Slack (futuro) | `chat.postMessage` + signing secret |
| Gmail (futuro) | Cola async / job; no bloquear worker HTTP del gateway |

## Extensiones futuras (interfaz mínima)

| Canal | Entrada | Salida | SLA webhook |
|-------|---------|--------|-------------|
| Slack | Events API + `X-Slack-Signature` | `chat.postMessage` | Responder 200 en &lt;3s; trabajo pesado en cola |
| Gmail | Pub/Sub push o polling job | `users.messages.send` / draft | Asíncrono; spec aparte |
| Otros | Adapter `normalize_inbound` → `ChatRequest` | `deliver_outbound` registrado por `channel` | Definir por canal |

## Seguridad

- No registrar tokens completos en logs ni LangSmith.
- Telegram Guard y ACL existentes aplican a **Telegram**; Discord requiere mapping de `user_id` → ACL en evolución (MVP: mismo `user_id` snowflake en `ChatRequest`).

## Coherencia ACID

- El db-writer singleton y cola Redis no cambian; solo el **origen** del `ChatRequest` difiere.
