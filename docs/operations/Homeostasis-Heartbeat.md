# Homeostasis Heartbeat (Demonio de Proactividad)

## Objetivo

El microservicio `services/heartbeat` se despierta de forma periódica, evalúa las creencias de homeostasis en DuckDB y, cuando detecta una anomalía, inyecta un **SYSTEM_EVENT** en el API Gateway. El agente decide si debe enviar un mensaje proactivo al usuario usando la herramienta `send_proactive_message`, que usa salida nativa (Bot API / webhook outbound del gateway).

## Flujo de alto nivel

1. `Heartbeat Daemon` ejecuta `run_heartbeat()` cada `HEARTBEAT_INTERVAL_SECONDS` (por defecto 1h).
2. Consulta DuckDB mediante `HomeostasisManager` para cada worker con `homeostasis_config`.
3. Si encuentra anomalías, aplica un control de spam (cooldown en Redis) por `tenant_id` + `belief_key`.
4. Cuando una alerta está permitida, hace `POST /api/v1/agent/chat` al Gateway con un payload:
   - `message`: `[SYSTEM_EVENT: ...]`
   - `chat_id`: `admin_chat_id` del tenant
   - `is_system_prompt`: `true`
5. El Gateway pasa `is_system_prompt` al grafo (campo `state["is_system_prompt"] = True`).
6. El agente homeostático (por ejemplo `finanz`) interpreta el evento y, si corresponde, llama a la herramienta `send_proactive_message(chat_id, message)`.
7. `send_proactive_message` hace `POST` al endpoint outbound del gateway (`DUCKCLAW_HEARTBEAT_WEBHOOK_URL`) con `{chat_id, text}` y cabecera `X-DuckClaw-Secret`.
8. El gateway envía el mensaje proactivo al usuario vía **Bot API nativa** (Telegram).

## Contrato de anomalías

El helper `_evaluate_homeostasis()` en `services/heartbeat/main.py` devuelve una lista de anomalías, donde cada item tiene al menos:

- `tenant_id`: identificador lógico del tenant/worker (por ejemplo, el schema Finance: `finance_worker`).
- `belief_key`: la creencia que está fuera de rango (ej. `presupuesto_mensual`).
- `observed_value`: último valor observado (o proxy inicial).
- `admin_chat_id`: chat donde se debe notificar (configurable vía `DUCKCLAW_ADMIN_CHAT_ID` o, en el futuro, tabla de configuración).

## Skill `send_proactive_message`

- **Ubicación**: `packages/agents/src/duckclaw/forge/skills/outbound_messaging.py`
- **Contrato**:

```python
@tool
def send_proactive_message(chat_id: str, message: str) -> str:
    """
    Usa esta herramienta para enviar un mensaje proactivo o una alerta al usuario.
    Solo úsala cuando un [SYSTEM_EVENT] te lo solicite.
    """
```

- Envía `POST DUCKCLAW_HEARTBEAT_WEBHOOK_URL` con:
  - JSON: `{"chat_id": "<id>", "text": "<mensaje>"}`.
  - Cabecera: `X-DuckClaw-Secret: DUCKCLAW_OUTBOUND_WEBHOOK_SECRET`.
- Registra la acción en DuckDB vía `append_task_audit(..., status="PROACTIVE_MESSAGE_SENT")` (best-effort).

## Configuración outbound (API Gateway)

1. Definir en `.env`:
   - `DUCKCLAW_HEARTBEAT_WEBHOOK_URL` — URL interna del gateway para DMs proactivos (o ruta que delegue a Bot API).
   - `DUCKCLAW_OUTBOUND_WEBHOOK_SECRET` — secreto compartido para cabecera `X-DuckClaw-Secret`.
   - `DUCKCLAW_DEFAULT_WORKER_ID` — worker por defecto en eventos `[SYSTEM_EVENT]` sin sesión previa.
2. El gateway valida el secreto y envía con `TELEGRAM_BOT_TOKEN` (Bot API nativa).
3. Opcional: `DUCKCLAW_ADMIN_CHAT_ID` para alertas de seguridad y homeostasis.

## Despliegue con PM2

El archivo `ecosystem.heartbeat.config.cjs` define el servicio:

```javascript
{
  name: "DuckClaw-Heartbeat",
  script: "uv",
  args: "run --project services/heartbeat python main.py",
  env: {
    REDIS_URL: "redis://localhost:6379/0",
    GATEWAY_URL: "http://localhost:8000/api/v1/agent/chat"
  }
}
```

Para arrancarlo:

```bash
pm2 start ecosystem.heartbeat.config.cjs
pm2 logs DuckClaw-Heartbeat
```

El wizard `duckops` podrá, en el futuro, gestionar este servicio igual que `DuckClaw-Gateway` y `DuckClaw-DB-Writer`.
