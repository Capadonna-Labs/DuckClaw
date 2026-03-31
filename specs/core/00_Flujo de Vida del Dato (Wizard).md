# Flujo de vida del dato en DuckClaw

Documento detallado del ciclo de vida de los datos: API Gateway, DB Writer, colas Redis, creación de `.duckdb` e integraciones n8n.

---

## 1. Visión general

```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                              INTEGRACIONES (n8n)                                         │
│  Telegram, webhooks, APIs externas → n8n orquesta y envía a DuckClaw-Gateway             │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                         DUCKCLAW API GATEWAY (puerto 8000)                               │
│  services/api-gateway/main.py — microservicio unificado                                 │
│  Agente, db/write, homeostasis, system health (todo integrado en main.py)                │
└─────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                    ┌─────────────────────┼─────────────────────┐
                    │                     │                     │
                    ▼                     ▼                     ▼
            ┌───────────────┐     ┌───────────────┐     ┌───────────────┐
            │  SELECT/READ  │     │ INSERT/UPDATE │     │  Fly commands │
            │  (directo)    │     │  (encolar)     │     │  /role, /tasks │
            └───────┬───────┘     └───────┬───────┘     └───────────────┘
                    │                     │
                    │                     ▼
                    │             ┌───────────────┐
                    │             │    REDIS      │
                    │             │ duckdb_write_  │
                    │             │    queue      │
                    │             └───────┬───────┘
                    │                     │
                    │                     ▼
                    │             ┌───────────────┐
                    │             │  DB WRITER    │
                    │             │  (singleton)  │
                    │             └───────┬───────┘
                    │                     │
                    └─────────────────────┼─────────────────────┐
                                          ▼                     │
                                  ┌───────────────┐             │
                                  │    DUCKDB     │◄────────────┘
                                  │ *.duckdb      │
                                  └───────────────┘
```

---

## 2. Componentes y rutas de scripts

### 2.1 API Gateway (microservicio unificado)


| Ruta                                  | Descripción                                                             |
| ------------------------------------- | ----------------------------------------------------------------------- |
| `services/api-gateway/main.py`        | Microservicio FastAPI. **Punto de entrada único** para todo el tráfico. |
| `services/api-gateway/core/config.py` | Config: `REDIS_URL` (o `DUCKCLAW_REDIS_URL`).                           |


**Endpoints (todos definidos en `services/api-gateway/main.py`):**

- `GET /`, `GET /health` — Root y health check.
- `POST /api/v1/db/write` — Encola escrituras en Redis.
- `POST /api/v1/agent/chat`, `POST /api/v1/agent/{worker_id}/chat`
- `GET /api/v1/agent/workers`, `GET /api/v1/agent/{worker_id}/history`
- `GET /api/v1/homeostasis/status`, `POST /api/v1/homeostasis/ask_task`
- `GET /api/v1/system/health`

**Arranque:** `duckops serve --pm2 --gateway` o `uvicorn main:app --app-dir services/api-gateway`

---

### 2.2 Dependencias del agente (usadas por el microservicio)


| Ruta                                                  | Descripción                                                                 |
| ----------------------------------------------------- | --------------------------------------------------------------------------- |
| `services/api-gateway/main.py`                        | Microservicio: importa `graph_server`, `gateway_db`, `on_the_fly_commands`. |
| `packages/agents/src/duckclaw/graphs/graph_server.py` | Grafo LangGraph, `get_db()`, `_ainvoke()`.                                 |
| `services/db-writer/core/config.py`                    | Ruta de la `.duckdb` (`DUCKDB_PATH`; por defecto `db/duckclaw.duckdb`).     |


---

### 2.3 Singleton Writer Bridge (API Gateway → Redis → DB Writer)


| Ruta                                 | Descripción                                                                 |
| ------------------------------------ | --------------------------------------------------------------------------- |
| `services/api-gateway/main.py`      | `POST /api/v1/db/write` encola en Redis. Rechaza SELECT.                    |
| `services/db-writer/main.py`        | Consumidor: BRPOP `duckdb_write_queue`, ejecuta `conn.execute(query, params)`. |
| `packages/agents/src/duckclaw/graphs/tools.py` | `admin_sql()` para escrituras (grafo dentro del Gateway).          |


**Flujo:**

1. Cliente envía `POST /api/v1/db/write` con `{"query", "params", "tenant_id"}`.
2. Gateway valida que no sea SELECT; genera `task_id`; hace `LPUSH duckdb_write_queue` con `{"task_id", "tenant_id", "query", "params"}`.
3. Redis mantiene la cola.
4. `services/db-writer` hace `BRPOP` y ejecuta `conn.execute(query, params)` en DuckDB.

**Arranque del consumidor:**

```bash
cd services/db-writer && python main.py
```

O como PM2: `DuckClaw-DB-Writer`.

---

### 2.4 DB Writer (services/db-writer)


| Ruta                                | Descripción                                                     |
| ----------------------------------- | --------------------------------------------------------------- |
| `services/db-writer/main.py`        | Consumidor async: BRPOP, ejecuta `conn.execute(query, params)`. |
| `services/db-writer/core/config.py` | `REDIS_URL`, `QUEUE_NAME`, `DUCKDB_PATH`.                       |


**Formato de mensaje esperado:** `{"task_id", "tenant_id", "query", "params"}`.

**Uso:** Pensado para el pipeline `services/api-gateway` → Redis → `services/db-writer`.

---

### 2.5 Redis y colas


| Variable de entorno        | Uso                                                                   |
| -------------------------- | --------------------------------------------------------------------- |
| `DUCKCLAW_WRITE_QUEUE_URL` | URL Redis para la cola de escritura (ej. `redis://localhost:6379/0`). |
| `DUCKCLAW_REDIS_URL`       | Alternativa usada por ActivityManager (`/tasks`), mismo Redis.        |


**Cola:** `duckdb_write_queue` (lista Redis, LPUSH por productores, BRPOP por consumidores).

---

### 2.6 Creación y esquema de la .duckdb


| Ruta                                                  | Descripción                                                                  |
| ----------------------------------------------------- | ---------------------------------------------------------------------------- |
| `packages/agents/src/duckclaw/workers/loader.py`      | `run_schema(db, spec)` — crea schema, `agent_beliefs`, ejecuta `schema.sql`. |
| `packages/agents/templates/workers/finanz/schema.sql` | DDL de tablas (cuentas, presupuestos, deudas, transacciones, etc.).          |
| `scripts/duckclaw_setup_wizard.py`                   | Wizard CLI: crea `db/<nombre>.duckdb` si no existe; gestiona PM2 (Gateway, DB Writer). |
| `packages/shared/scripts/recreate_gateway_db.py`      | Recrea la DB del Gateway con schema Finanz.                                  |
| `packages/shared/scripts/apply_finanz_schema.py`      | Aplica tablas Finanz a una `.duckdb` existente.                              |


**Flujo de creación:**

1. Al cargar un worker (ej. finanz), `run_schema(db, spec)` en `factory.py`.
2. `CREATE SCHEMA IF NOT EXISTS <schema_name>`.
3. `CREATE TABLE IF NOT EXISTS agent_beliefs`.
4. Ejecución de `templates/workers/<worker>/schema.sql`.

**Ruta por defecto:** `DUCKCLAW_DB_PATH` en `.env` o `db/gateway.duckdb` (relativo a la raíz del repo).

---

### 2.7 Integraciones n8n


| Ruta                                          | Descripción                     |
| --------------------------------------------- | ------------------------------- |
| `packages/shared/docs/n8n-workflow-review.md` | Configuración del workflow n8n. |
| `packages/shared/docs/n8n-troubleshooting.md` | Troubleshooting.                |


**Flujo n8n:**

1. Trigger (Telegram, webhook, etc.) recibe el mensaje.
2. HTTP Request al **API Gateway** (`services/api-gateway/main.py`) en `http://<IP>:8000/api/v1/agent/chat`.
3. El Gateway procesa la petición (agente, fly commands, grafo LangGraph) — todo en `main.py`.
4. Para escrituras directas: `POST /api/v1/db/write` → Redis → DB Writer.
5. Headers: `X-Tailscale-Auth-Key: <DUCKCLAW_TAILSCALE_AUTH_KEY>`.
6. Responder (Telegram, etc.) envía la respuesta al usuario.

Todo el tráfico pasa por el microservicio `services/api-gateway`.

---

### 2.8 Scripts de sincronización e inicialización


| Ruta                                                    | Descripción                                        |
| ------------------------------------------------------- | -------------------------------------------------- |
| `packages/shared/scripts/sync_telegram_duckdb.sh`       | Sincroniza `telegram.duckdb` desde el VPS (rsync). |
| `packages/shared/scripts/install_duckclaw.sh`           | Instalación general.                               |
| `packages/shared/scripts/validate_ibkr_connectivity.sh` | Valida conectividad con IBKR/Capadonna.            |
| `packages/shared/scripts/validate_cuentas_gateway.py`   | Valida tabla `cuentas` en la DB del Gateway.       |
| `packages/shared/scripts/inspect_telegram_db.py`        | Inspecciona tablas de la DB del Gateway.           |


---

### 2.9 Tests del pipeline


| Ruta                                     | Descripción                                                  |
| ---------------------------------------- | ------------------------------------------------------------ |
| `tests/run_singleton_writer_pipeline.py` | Tests del pipeline API Gateway → Redis → DB Writer → DuckDB. |


---

## 3. Flujo detallado paso a paso

### 3.1 Mensaje de usuario (Telegram / n8n)

1. Usuario envía mensaje en Telegram.
2. n8n recibe el webhook de Telegram.
3. n8n hace `POST /api/v1/agent/chat` al DuckClaw-Gateway (Mac Mini :8000).
4. Middleware valida `X-Tailscale-Auth-Key`.

### 3.2 Procesamiento en el Gateway

1. `services/api-gateway/main.py` recibe la petición en `agent_chat()`.
2. `_invoke_chat()` procesa el mensaje.
3. Si el mensaje empieza por `/` → `handle_command()` (fly commands) → respuesta inmediata.
4. Si no: `graph_server._get_or_build_graph()` → `_ainvoke(graph, message, ...)`.
5. `set_busy(session_id, task=message)` en Redis (ActivityManager).
6. El grafo invoca el agente (Finanz, etc.) con herramientas.

### 3.3 Ejecución del agente (admin_sql)

1. El LLM decide usar `admin_sql` con una query.
2. `tools.admin_sql(db, query)`:
  - Si es SELECT/WITH/SHOW/DESCRIBE → `db.query(q)` directo.
  - Si es INSERT/UPDATE/DELETE/CREATE:
    - Si `DUCKCLAW_WRITE_QUEUE_URL` está definido → `enqueue_write(sql)` → Redis LPUSH.
    - Si no → `db.execute(q)` directo.
3. Respuesta al LLM: `{"status": "ok", "queued": true}` o resultado de la query.

### 3.4 Consumidor de la cola (DB Writer)

1. `singleton_writer.run_consumer()` en bucle:
2. `BRPOP duckdb_write_queue` (bloqueante).
3. Parsea JSON: `{"sql": "...", "db_path": "..."}`.
4. `db.execute(sql)` sobre la DuckDB indicada.
5. Log de éxito o error.

### 3.5 Finalización

1. `set_idle(session_id)` en Redis.
2. `append_task_audit()` en `task_audit_log` (DuckDB).
3. Respuesta al Gateway → n8n → Telegram.

---

## 4. Variables de entorno clave


| Variable                      | Uso                                                 |
| ----------------------------- | --------------------------------------------------- |
| `DUCKCLAW_DB_PATH`            | Ruta de la `.duckdb` (ej. `db/duckclawdb2.duckdb`). |
| `DUCKCLAW_WRITE_QUEUE_URL`    | Redis para la cola de escritura.                    |
| `DUCKCLAW_REDIS_URL`          | Redis para ActivityManager (`/tasks`).              |
| `DUCKCLAW_TAILSCALE_AUTH_KEY` | Auth para n8n y clientes.                           |
| `DUCKCLAW_LLM_PROVIDER`       | Proveedor LLM (deepseek, mlx, etc.).                |


---

## 5. Resumen de scripts por función


| Función                                   | Scripts                                                                                |
| ----------------------------------------- | -------------------------------------------------------------------------------------- |
| **API Gateway (microservicio unificado)** | `services/api-gateway/main.py`                                                         |
| **Encolar escrituras**                    | `packages/agents/src/duckclaw/forge/homeostasis/singleton_writer.py` (`enqueue_write`) |
| **Consumir cola (forge)**                 | `python -m duckclaw.forge.homeostasis.singleton_writer --consume`                     |
| **Consumir cola (api-gateway)**           | `services/db-writer/main.py`                                                           |
| **admin_sql**                           | `packages/agents/src/duckclaw/graphs/tools.py`                                         |
| **Crear schema**                          | `packages/agents/src/duckclaw/workers/loader.py` (`run_schema`)                        |
| **Schema Finanz**                         | `packages/agents/templates/workers/finanz/schema.sql`                                  |
| **Ruta DB**                               | `services/db-writer/core/config.py` (`DUCKDB_PATH`)                                   |
| **Sincronizar VPS**                       | `packages/shared/scripts/sync_telegram_duckdb.sh`                                      |
| **Tests pipeline**                        | `tests/run_singleton_writer_pipeline.py`                                               |

---

## 6. Wizard y pipeline completo

El wizard es el punto de entrada para configurar y desplegar todo el pipeline. Hay dos implementaciones:

- **Legacy (Rich):** `duckops init` → `scripts/duckclaw_setup_wizard.py` — flujo secuencial con Rich; persistente en pasos intermedios.
- **Sovereign v2.0:** `duckops sovereign` o `duckops init --sovereign` — máquina de estados, lenguaje soberano en UI, borrador hasta *Review & Deploy*; spec dedicada `specs/features/DuckClaw Sovereign Wizard (v2.0).md`.

Sustituye scripts `.sh` por un CLI en Python: mantenible, cross-platform (macOS, Linux, Windows) y con control de datos sensibles (Habeas Data).

### 6.1 Comandos duckops

| Comando | Descripción |
|---------|-------------|
| `duckops init [tenant_id]` | Ejecuta el wizard interactivo legacy (Rich). Invoca `scripts/duckclaw_setup_wizard.py`. |
| `duckops init --sovereign` | Wizard Sovereign v2.0 (mismo efecto que `duckops sovereign`). |
| `duckops sovereign` | Wizard Sovereign v2.0 (TUI `prompt_toolkit`, borrador + confirmación). |
| `duckops serve [--pm2] [--gateway]` | Arranca el API Gateway (`services/api-gateway`) o servidor LangGraph. Con `--gateway` genera `ecosystem.api.config.cjs` y despliega DuckClaw-Gateway en PM2. Carga `.env` para propagar `DUCKCLAW_LLM_PROVIDER`, `REDIS_URL`, etc. |
| `duckops deploy [--provider]` | Despliega DuckClaw-Brain (bot Telegram) como servicio persistente (PM2, systemd, Windows). |
| `duckops audit` | Muestra configuración con datos sensibles enmascarados. |

### 6.2 Cómo el wizard lleva a cabo el pipeline

**Paso 0 — Detección de servicios PM2**

Al iniciar, el wizard lista los procesos PM2 detectados. Si el usuario elige "Gestionar servicio de persistencia", puede editar:

- **DuckClaw-Gateway**: Regenera `ecosystem.api.config.cjs` vía `duckops serve --pm2 --gateway`. Escribe `DUCKCLAW_DB_PATH` y `DUCKDB_PATH` en `.env`. El Gateway encola escrituras en Redis y sirve el agente.
- **DuckClaw-DB-Writer**: Genera `ecosystem.db-writer.config.cjs` con `cwd=services/db-writer`, `REDIS_URL` y `DUCKDB_PATH`. El consumidor hace BRPOP sobre `duckdb_write_queue` y escribe en DuckDB.
- **DuckClaw-Brain**: Genera `ecosystem.core.config.cjs` para el bot Telegram (polling directo, sin pasar por n8n).

**Configuración de la base de datos**

- **Prioridad:** `DUCKCLAW_DB_PATH` en `.env` → `~/.config/duckclaw/wizard_config.json` → `db/duckclaw.duckdb`.
- **Normalización:** Cualquier ruta se normaliza a `db/<nombre>.duckdb` respecto a la raíz del repo.
- **Compatibilidad:** Al escribir `DUCKCLAW_DB_PATH`, el wizard escribe también `DUCKDB_PATH` para que `services/db-writer` use la misma ruta.
- **Creación automática:** Al confirmar o guardar, se crea el archivo `.duckdb` en `db/` si no existe.

**Flujo completo (wizard → pipeline operativo)**

1. Usuario ejecuta `duckops init`.
2. Wizard detecta PM2 y ofrece gestionar DuckClaw-Gateway, DuckClaw-DB-Writer o DuckClaw-Brain.
3. Si gestiona **Gateway**: regenera config, escribe `.env`, reinicia PM2. El Gateway queda listo para recibir tráfico de n8n.
4. Si gestiona **DB Writer**: genera `ecosystem.db-writer.config.cjs`, inicia o reinicia el consumidor. Redis → DuckDB queda operativo.
5. Si gestiona **Brain** o completa el wizard: configura token, LLM, DB; despliega con PM2/systemd; opcionalmente arranca el bot.
6. Pipeline operativo: n8n → Gateway → (agente / db/write) → Redis → DB Writer → DuckDB.

### 6.3 Estructura del CLI duckops

```
packages/duckops/
├── pyproject.toml
└── duckops/
    ├── cli.py              # duckops sovereign + add_typer init/serve/deploy/audit
    ├── sovereign/        # Wizard v2.0 (draft, materialize, ui)
    └── commands/
        ├── init.py         # duckops init → wizard legacy o --sovereign
        ├── serve.py        # duckops serve (Gateway, LangGraph)
        ├── deploy.py       # duckops deploy (PM2, systemd, Windows)
        └── audit.py        # duckops audit (Habeas Data)
```

El script `install_duckclaw.sh` usa `duckops init` cuando está instalado; si no, ejecuta el wizard directamente.


