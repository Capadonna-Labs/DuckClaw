# Interfaz de Control de Agentes (Fly Commands)

## 1. Objetivo Arquitectónico

Exponer comandos de chat que permitan al usuario **mutar el estado del agente en caliente** (sin reiniciar PM2) y **consultar configuración y capacidades**. Los fly commands se ejecutan **antes** de invocar el grafo LangGraph; si el mensaje empieza por `/`, se parsea, ejecuta y retorna la respuesta directamente.

**Canales soportados:** Telegram (bot directo) y API Gateway (n8n → Telegram). En ambos casos, el usuario puede enviar `/role finanz` o `/skills` y obtener una respuesta inmediata.

---

## 2. Ubicación e Integración

| Componente | Ubicación | Responsabilidad |
|------------|-----------|------------------|
| **Lógica de comandos** | `packages/agents/src/duckclaw/graphs/on_the_fly_commands.py` | `handle_command()`, `parse_command()`, ejecutores por comando |
| **Telegram bot** | `packages/agents/src/duckclaw/graphs/telegram_bot.py` | Intercepta `/` antes del grafo; llama `handle_command(db, chat_id, text)` |
| **API Gateway** | `services/api-gateway/main.py` | Intercepta `/` en `_invoke_chat`; llama `handle_command(db, session_id, message)` |
| **Persistencia** | Tabla `agent_config` en DuckDB | Claves por chat/sesión: `chat_{id}_worker_id`, `chat_{id}_llm_provider`, etc. |
| **Heartbeat (observabilidad)** | `packages/agents/src/duckclaw/graphs/chat_heartbeat.py` | Flag en Redis `duckclaw:heartbeat:{tenant_id}:{chat_id}` (TTL 7 días); DMs vía `N8N_OUTBOUND_WEBHOOK_URL` en hilo daemon |

**Flujo:** Mensaje → ¿Empieza por `/`? → `handle_command()` → Si retorna string, enviar y terminar. Si retorna `None`, invocar el grafo.

---

## 3. Comandos Implementados

### A. `/role [worker_id]`

Cambia el rol (worker template) en caliente. Siempre hay un rol activo; por defecto: `personalizable` (para armar con /prompt, skills y goals).

| Uso | Comportamiento |
|-----|----------------|
| `/role` | Muestra rol actual y plantillas disponibles (personalizable, finanz, support, powerseal, research_worker) |
| `/role finanz` | Asigna worker `finanz`; confirma con nombre y capacidades |
| `/role personalizable` | Rol base personalizable (read_sql, admin_sql, inspect_schema por defecto) |

**Persistencia:** `agent_config` → `chat_{id}_worker_id`

### B. `/skills`

Lista las herramientas habilitadas para el rol actual. Si hay `worker_id`, usa el manifest del worker; si no, muestra herramientas por defecto (read_sql, admin_sql, inspect_schema, manage_memory).

### C. `/forget`

Borra el historial de conversación del chat/sesión. En Telegram: `telegram_conversation`. En API: `api_conversation`. También limpia `last_audit`. Cumple Habeas Data (supresión solicitada por el usuario).

### D. `/context on | off`

Activa o desactiva la inyección de RAG (memoria a largo plazo) en el prompt. `use_rag=false` reduce el historial a 3 turnos.

### D2. `/heartbeat [on | off]`

Observabilidad en tiempo real para el usuario: si está **on**, el gateway envía DMs breves al `chat_id` por el webhook de salida (mismo contrato que n8n) al delegar al worker, **antes de cada tool** y justo antes de cerrar la respuesta. Requiere **Redis** (`REDIS_URL` / `DUCKCLAW_REDIS_URL`) y **`N8N_OUTBOUND_WEBHOOK_URL`**. El POST outbound corre en hilo **fire-and-forget** (no bloquea el agente). Persistencia: clave canónica `duckclaw:heartbeat:{tenant_id}:{chat_id}` más alias `duckclaw:heartbeat:chat:{chat_id}` (y lectura de `DUCKCLAW_GATEWAY_TENANT_ID` si aplica) para que el flag coincida entre fly command y worker aunque el `tenant_id` del estado del grafo difiera.

### E. `/audit`

Muestra la última evidencia de ejecución: SQL, latencia, tokens, `run_id` LangSmith. Requiere que el grafo haya guardado evidencia previamente (`save_last_audit`).

### E2. `/history [n]`

Historial de tareas ejecutadas (auditoría de rendimiento). Sin args: últimas 5. Con número: últimas n (máx. 20). Muestra task_id, ✅/❌, duración, acción. Incluye promedio de ejecución y tareas fallidas (24h). Tabla `task_audit_log`.

### F. `/health`

Estado de infraestructura: DuckDB, MLX (si aplica), latencia. Útil para diagnóstico sin acceder al servidor.

### F2. `/lake` | `/lake status`

Diagnóstico del acceso SSH al **Lake Capadonna** (variables `CAPADONNA_*` en el proceso del gateway, resolución de clave `-i`, semántica 0/1 alineada con `finance_worker.agent_beliefs` para `lake_host_configured` / `lake_status_online`, y prueba rápida `ssh -o BatchMode=yes -o ConnectTimeout=5 user@host true` cuando la config es válida). No ingiere OHLCV; para datos reales usar la tool `fetch_lake_ohlcv` o `fetch_market_data`.

### F3. `/sensors`

Resumen en un solo mensaje de sensores y rutas de datos del **proceso del gateway**: DuckDB local (`SELECT 1` sobre la sesión activa), **IBKR** (portafolio vía `GET` a `IBKR_PORTFOLIO_API_URL` con clave; mercado OHLC vía `GET` mínimo a `IBKR_MARKET_DATA_URL` con parámetros de prueba; timeouts cortos), **Lake Capadonna** (misma prueba SSH compacta que `/lake`), **Tavily** (presencia de `tavily-python` y `TAVILY_API_KEY`; sin llamada a la API para no gastar cuota), **Reddit MCP** (librería MCP, env Reddit completo, `npx` en PATH), **Google Trends MCP** (librería MCP y comando stdio resuelto para `google-trends-mcp` / `uvx`), **Browser sandbox** (manifest `finanz` → `browser_sandbox`, Docker ping, imagen `STRIX_BROWSER_IMAGE` / `duckclaw/browser-env:latest` presente localmente, y `security_policy.yaml` finanz: red bridge vs deny para HTTP en Playwright). Tavily, Reddit y Trends reflejan **capacidad y configuración en el proceso**, no un health end-to-end del servicio externo salvo donde se indica (IBKR y SSH lake).

### G. `/approve` | `/reject`

Autoriza o deniega una operación retenida por SQLValidator o SandboxPipeline (grafo en `interrupt`). HITL para acciones sensibles.

### H. `/prompt [texto]` | `/system_prompt` | `/system`

Sin args: muestra el system prompt actual (del worker o modificado). Con args: actualiza el system prompt global. Persiste en `agent_config` (clave global).

### I. `/model [provider=...] [model=...] [base_url=...]` | `/provider` | `/llm`

Sin args: muestra provider, model y base_url actuales. Con args: actualiza en caliente. Ej: `/model provider=deepseek` o `/model provider=mlx | model=Slayer-8B`.

### J. `/setup [key=value | key=value]`

Formato compatible con Telegram. Sin args: muestra config (llm_provider, llm_model, worker_id, system_prompt). Con args: actualiza. Ej: `/setup llm_provider=deepseek | system_prompt=Eres un experto...`

---

## 4. Formato de Respuesta (Telegram-Safe)

Las respuestas de los fly commands se envían a Telegram (directo o vía n8n). Si el nodo "Responder Telegram" usa `parse_mode=Markdown`, caracteres como `_`, `*`, `` ` ``, `[` pueden provocar "Can't find end of entity".

**Solución:** La función `_telegram_safe()` escapa esos caracteres en todas las salidas. Se evita Markdown bold (`**`) y se usan guiones `-` en lugar de bullets `•` para listas. Los nombres de skills con underscore (ej. `insert_transaction`) se escapan como `insert\_transaction`.

---

## 5. API Gateway (n8n)

Cuando n8n orquesta el flujo Telegram → DuckClaw API Gateway → Responder Telegram:

1. **Endpoint:** `POST /api/v1/agent/chat` (no `/api/v1/agent/finanz/chat`)
2. **Body:** `{"message": "/role finanz", "session_id": "1726618406"}`
3. **Respuesta:** `{"response": "✅ Rol cambiado a...", "session_id": "...", "worker_id": "finanz", "elapsed_ms": 0}`

El `session_id` identifica la sesión; el `worker_id` y el system prompt se persisten por sesión en `agent_config`. El endpoint genérico respeta `/role` para cambiar de trabajador virtual por sesión.

**n8n:** El nodo "Responder Telegram" debe enviar `response` al chat. Si usa `parse_mode=Markdown`, las respuestas ya están escapadas. Si persisten errores, desactivar `parse_mode` para enviar texto plano.

---

## 6. Persistencia (agent_config)

| Clave (ejemplo) | Descripción |
|-----------------|-------------|
| `chat_1726618406_worker_id` | Worker activo (finanz, support, etc.) |
| `chat_1726618406_llm_provider` | Proveedor LLM por sesión |
| `chat_1726618406_llm_model` | Modelo LLM por sesión |
| `chat_1726618406_llm_base_url` | URL base del LLM |
| `chat_1726618406_use_rag` | RAG on/off |
| `chat_1726618406_last_audit` | JSON de última ejecución (SQL, latency, run_id) |
| `system_prompt` (global) | System prompt modificado |

---

## 7. Comandos /goals y /tasks (Implementados)

### `/goals [--reset]`

Consulta creencias del HomeostasisManager (tabla `agent_beliefs` por worker). Requiere `/role <worker_id>` con homeostasis (finanz, powerseal).

| Uso | Comportamiento |
|-----|----------------|
| `/goals` | Lista beliefs: target, observed, delta, estado (equilibrio/anomalía) |
| `/goals --reset` | Borra `observed_value` de todas las creencias |

### `/tasks`

Estado del ActivityManager (Redis). El Gateway y el bot Telegram marcan BUSY al invocar el grafo e IDLE al terminar.

| Uso | Comportamiento |
|-----|----------------|
| `/tasks` | Muestra: Estado (IDLE/BUSY), tarea actual, tiempo en ejecución |

**Redis:** Usa `DUCKCLAW_REDIS_URL` o `DUCKCLAW_WRITE_QUEUE_URL`. Sin Redis, retorna "IDLE (sin Redis para ActivityManager)".

---

## 8. Habeas Data y Auditoría

- **Transparencia:** `/audit` expone la última evidencia (SQL, tokens, run_id). El usuario puede ver qué ejecutó el agente.
- **Supresión:** `/forget` borra historial bajo solicitud explícita del usuario.
- **Control:** `/role`, `/prompt`, `/model` permiten ajustar el comportamiento sin reiniciar el servicio.
