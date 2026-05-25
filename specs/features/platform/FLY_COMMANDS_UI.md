# Interfaz de Control de Agentes (Fly Commands)

## 1. Objetivo Arquitectónico

Exponer comandos de chat que permitan al usuario **mutar el estado del agente en caliente** (sin reiniciar PM2) y **consultar configuración y capacidades**. Los fly commands se ejecutan **antes** de invocar el grafo LangGraph; si el mensaje empieza por `/`, se parsea, ejecuta y retorna la respuesta directamente.

**Canales soportados:** Telegram (Bot API nativa / webhook inbound) y API Gateway direct. En ambos casos, el usuario puede enviar `/role finanz` o `/skills` y obtener una respuesta inmediata.

---

## 2. Ubicación e Integración

| Componente | Ubicación | Responsabilidad |
|------------|-----------|------------------|
| **Lógica de comandos** | `packages/agents/src/duckclaw/graphs/on_the_fly_commands.py` | `handle_command()`, `parse_command()`, ejecutores por comando |
| **Telegram bot** | `packages/agents/src/duckclaw/graphs/telegram_bot.py` | Intercepta `/` antes del grafo; llama `handle_command(db, chat_id, text)` |
| **API Gateway** | `services/api-gateway/main.py` | Intercepta `/` en `_invoke_chat`; llama `handle_command(db, session_id, message)` |
| **Persistencia** | Tabla `agent_config` en DuckDB | Claves por chat/sesión: `chat_{id}_worker_id`, `chat_{id}_llm_provider`, etc. |
| **Heartbeat (observabilidad)** | `packages/agents/src/duckclaw/graphs/chat_heartbeat.py` | Flag en Redis `duckclaw:heartbeat:{tenant_id}:{chat_id}` (TTL 7 días); DMs vía `DUCKCLAW_HEARTBEAT_WEBHOOK_URL` en hilo daemon |

**Flujo:** Mensaje → ¿Empieza por `/`? → `handle_command()` → Si retorna string, enviar y terminar. Si retorna `None`, invocar el grafo.

---

## 3. Comandos Implementados

### A. `/role [worker_id]`

Cambia el rol (worker template) en caliente. Siempre hay un rol activo; por defecto: `personalizable` (para armar con /prompt, skills y `/crons`).

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

### D1b. `/ibkr on --mode paper|live` | `/ibkr off`

Habilita o deshabilita la skill **`get_ibkr_portfolio`** por sesión (Finanz). Con `on`, **`--mode paper` o `--mode live` es obligatorio**. Persistencia: `ibkr_enabled`, `ibkr_portfolio_mode` en `agent_config`. Default Finanz: tool oculta hasta `/ibkr on`.

### D2. `/heartbeat [on | off]`

Observabilidad en tiempo real para el usuario: si está **on**, el gateway envía DMs breves al `chat_id` por salida nativa (Bot API / `DUCKCLAW_HEARTBEAT_WEBHOOK_URL`) al delegar al worker, **antes de cada tool** y justo antes de cerrar la respuesta. Requiere **Redis** (`REDIS_URL` / `DUCKCLAW_REDIS_URL`) y **`DUCKCLAW_HEARTBEAT_WEBHOOK_URL`**. El POST outbound corre en hilo **fire-and-forget** (no bloquea el agente). Persistencia: clave canónica `duckclaw:heartbeat:{tenant_id}:{chat_id}` más alias `duckclaw:heartbeat:chat:{chat_id}` (y lectura de `DUCKCLAW_GATEWAY_TENANT_ID` si aplica) para que el flag coincida entre fly command y worker aunque el `tenant_id` del estado del grafo difiera.

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

Las respuestas de los fly commands se envían a Telegram (Bot API nativa o gateway). Si el envío usa `parse_mode=Markdown`, caracteres como `_`, `*`, `` ` ``, `[` pueden provocar "Can't find end of entity".

**Solución:** La función `_telegram_safe()` escapa esos caracteres en todas las salidas. Se evita Markdown bold (`**`) y se usan guiones `-` en lugar de bullets `•` para listas. Los nombres de skills con underscore (ej. `insert_transaction`) se escapan como `insert\_transaction`.

---

## 5. API Gateway direct

Cuando el flujo es Telegram webhook inbound → DuckClaw API Gateway → respuesta al chat:

1. **Endpoint:** `POST /api/v1/agent/chat` (no `/api/v1/agent/finanz/chat`; worker por sesión vía `DUCKCLAW_DEFAULT_WORKER_ID` o `/role`)
2. **Body:** `{"message": "/role finanz", "session_id": "1726618406", "chat_id": "1726618406"}`
3. **Respuesta:** `{"response": "✅ Rol cambiado a...", "session_id": "...", "worker_id": "finanz", "elapsed_ms": 0}`

El `session_id` / `chat_id` identifica la sesión; el `worker_id` y el system prompt se persisten por sesión en `agent_config`. El endpoint genérico respeta `/role` para cambiar de trabajador virtual por sesión.

**Telegram:** El gateway envía `response` al chat vía Bot API. Si usa `parse_mode=Markdown`, las respuestas ya están escapadas (`_telegram_safe`). Si persisten errores, enviar texto plano sin `parse_mode`.

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

## 7. Comandos `/crons` y `/tasks` (Implementados)

El nombre de usuario del comando es **`/crons`** (cron jobs + revisión de objetivos homeostasis). Se acepta **`/goals`** como alias silencioso por compatibilidad; la persistencia en DuckDB sigue usando el prefijo interno `goals_*` en `agent_config` (estabilidad; no requiere migración).

### `/crons [--reset] [--delta …] [--timestamp …] [--rm …]`

Consulta creencias del HomeostasisManager (tabla `agent_beliefs` por worker). El registro de claves por defecto para autocompletar objetivos viene del **worker activo** del chat (`/role` / estado del gateway), con fallback al primer template que tenga `homeostasis.yaml`. Con **Quant-Trader** activo, un goal de drawdown máximo se refleja también en `quant_core.trading_risk_constraints` en la bóveda (ver [Quant_Trading_Session_Homeostasis.md](Quant_Trading_Session_Homeostasis.md)).

| Uso | Comportamiento |
|-----|----------------|
| `/crons` | Lista en dos bloques: **Tus crons** — bloque 🎯 Manager (objetivos homeostasis) y, cuando aplica, un subtítulo unificado **`Revisión proactiva`** (o **`Revisión proactiva (TRADING_TICK)`** si `goals_delta_meta.trigger` es `trading_session`) con: intervalo humanizado y **cron-id `delta`** cuando `goals_delta_seconds` > 0 (más cuenta atrás aproximada si hay anclas), mensaje explícito de inconsistencia si hay meta `trading_session` pero intervalo apagado, línea opcional **Sesión Quant** (`session_uid` acortado si es tipo UUID largo; origen `schedule_quant_trading_proactive_ticks` / `/trading-session`); horario de reloj con **cron-id `wall`** en nota aparte si hay `--timestamp` — y **Del bot (infraestructura)** (intervalos del escaneo de DuckDB del ticker, ciclo homeostasis del daemon, y si el gateway embebido puede correr el mismo escaneo). Los números salen de `GOALS_TICKER_POLL_SECONDS`, `HEARTBEAT_INTERVAL_SECONDS` y `DUCKCLAW_EMBED_GOALS_TICKER` en el host. |
| `/crons --reset` | Borra goals del chat y la revisión proactiva (`--delta`); en Quant limpia riesgo en bóveda si aplica |
| `/crons --delta 20min` | Programa revisión periódica (mín. 60s, máx. 7d). Unidades: `s`, `m`/`min`, `h`. Guarda `goals_delta_seconds`, `goals_proactive_tenant_id`, anclas de schedule y **`goals_delta_meta` con `trigger: goals_cli`**. **Borra** `goals_cron_wall` si existía (exclusivo con `--timestamp`). Establece `goals_proactive_last_fire_epoch` al **momento actual** para que el primer tick espere el intervalo completo (no el siguiente poll del gateway ~45s). |
| `/crons --delta off` | Desactiva **solo** la programación por intervalo (`goals_delta_seconds` y anclas relacionadas; meta con `trigger: goals_cli`). **No** borra `goals_cron_wall` ni el horario `--timestamp`. Sincroniza en hub + bóvedas del mismo `db/private/<uid>/` (misma regla multiplex que antes). |
| `/crons --timestamp once YYYY-MM-DDTHH:MM` | Horario de reloj (zona por defecto `America/Bogota`, override `DUCKCLAW_CRONS_WALL_TZ`): una sola ejecución. Persiste JSON en `agent_config` → `chat_{id}_goals_cron_wall`; pone `goals_delta_meta.trigger = goals_wall` salvo que ya exista `trading_session`. **Exclusivo** con `--delta`: al guardar `--timestamp` se limpia el intervalo (equivalente a apagar solo la parte delta). Tras un tick exitoso, tipo `once` se elimina el JSON del wall. |
| `/crons --timestamp every HH:MM [weekdays\|lun mar …]` | Repetición diaria o en días concretos (`weekdays` = lun–vie). Misma persistencia y exclusividad que `once`. |
| `/crons --timestamp off` | Borra **solo** `goals_cron_wall` (local + bóvedas hermanas); no modifica `--delta`. |
| `/crons --rm delta` | Igual que `/crons --delta off`: quita solo la programación por intervalo. Alias del cron-id: `interval`. No modifica el horario de reloj. |
| `/crons --rm wall` | Igual que `/crons --timestamp off`: quita solo el horario de reloj. Alias: `timestamp`. No modifica `--delta`. |

**Ticker:** `services/heartbeat/main.py` (`_run_goals_proactive_tick`) escanea cada `GOALS_TICKER_POLL_SECONDS` (default 45s) el DuckDB del hub (`get_gateway_db_path()`) **y** todos los `*.duckdb` bajo `db/private/*/` (misma convención que el multiplex Telegram: los fly commands escriben en la bóveda del usuario, p. ej. `quant_traderdb1.duckdb`, distinta del hub `finanzdb1.duckdb`). Override: `DUCKCLAW_GOALS_TICKER_DB_PATH` fuerza una sola ruta (tests o despliegue especial). Además lee `chat_%_goals_cron_wall` para disparos por horario de reloj cuando `goals_delta_seconds` es 0 (exclusión con intervalo: no se deben activar ambos). Si `worker_id` del chat es `manager` o vacío, no se dispara **salvo** heurística multiplex: tenant `goals_proactive_tenant_id` = `Cuantitativo` → worker efectivo `Quant-Trader`. Tras un POST 2xx al gateway (`/api/v1/agent/{worker_id}/chat` con `is_system_prompt` y `skip_session_lock`), se actualiza `goals_proactive_last_fire_epoch` **en el mismo archivo** donde se encontró el schedule. Sin goals y sin meta `trading_session` / `goals_wall`, el ticker limpia el schedule en ese archivo. El mensaje sintético visible al modelo incluye «Revisión periódica de `/crons`» (tras despliegue; el código sigue aceptando el texto heredado con `/goals` para eventos en vuelo).

**Multiplex:** el ticker embebido en el API Gateway reutiliza la misma lógica de escaneo; con varios gateways PM2, cada proceso sigue recorriendo las mismas rutas bajo `db/private/` (idempotencia por chat + `last_fire`).

| Clave `agent_config` | Uso |
|---------------------|-----|
| `chat_{id}_goals_delta_seconds` | Intervalo en segundos (>0 activo) |
| `chat_{id}_goals_proactive_tenant_id` | Tenant efectivo al ejecutar `/crons --delta` |
| `chat_{id}_goals_proactive_last_fire_epoch` | Ultimo tick exitoso (epoch float) |
| `chat_{id}_goals_proactive_schedule_anchor_epoch` | Momento en que se ejecutó `/crons --delta` (epoch); la UI estima “próximo en” como ancla + intervalo hasta el primer tick |
| `chat_{id}_goals_cron_wall` | JSON v1: horario de reloj (`once` o `every` + días opcionales); ver paquete `cron_wall_schedule` |

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
