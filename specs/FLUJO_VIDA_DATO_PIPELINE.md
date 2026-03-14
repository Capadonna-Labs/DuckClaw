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


**Endpoints (todos definidos en `main.py`):**

- `GET /`, `GET /health` — Root y health check.
- `POST /api/v1/db/write` — Encola escrituras en Redis.
- `POST /api/v1/agent/chat`, `POST /api/v1/agent/{worker_id}/chat`
- `GET /api/v1/agent/workers`, `GET /api/v1/agent/{worker_id}/history`
- `GET /api/v1/homeostasis/status`, `POST /api/v1/homeostasis/ask_task`
- `GET /api/v1/system/health`

**Arranque:** `duckops serve --pm2 --gateway` o `uvicorn main:app --app-dir services/api-gateway`

---

### 2.2 Dependencias del agente (usadas por el Gateway)


| Ruta                                                  | Descripción                                                                 |
| ----------------------------------------------------- | --------------------------------------------------------------------------- |
| `packages/agents/src/duckclaw/api/gateway.py`         | Re-export de la app para compatibilidad (tests, `run_gateway`).             |
| `packages/agents/src/duckclaw/agents/graph_server.py` | Grafo LangGraph, `get_db()`, `_ainvoke()` — importado desde `main.py`.      |
| `packages/agents/src/duckclaw/gateway_db.py`          | Ruta de la `.duckdb` (`DUCKCLAW_DB_PATH`).                                  |


---

### 2.3 Singleton Writer Bridge (agente → Redis → DuckDB)


| Ruta                                                                 | Descripción                                                             |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `packages/agents/src/duckclaw/forge/homeostasis/singleton_writer.py` | `enqueue_write()`, `run_consumer()`. Cola `duckdb_write_queue`.         |
| `packages/agents/src/duckclaw/agents/tools.py`                       | `run_sql()` llama a `enqueue_write()` para INSERT/UPDATE/DELETE/CREATE. |


**Flujo:**

1. `run_sql()` en `tools.py` detecta escritura (no SELECT/WITH/SHOW/DESCRIBE).
2. Si `DUCKCLAW_WRITE_QUEUE_URL` está definido → `enqueue_write(sql)`.
3. Redis `LPUSH duckdb_write_queue` con `{"sql": "...", "db_path": "..."}`.
4. `run_consumer()` hace `BRPOP` y ejecuta `db.execute(sql)`.

**Arranque del consumidor:**

```bash
python -m duckclaw.forge.homeostasis.singleton_writer --consume
```

O como PM2: `DuckClaw-DB-Writer`.

---

### 2.4 DB Writer (services/db-writer)


| Ruta                                | Descripción                                                     |
| ----------------------------------- | --------------------------------------------------------------- |
| `services/db-writer/main.py`        | Consumidor async: BRPOP, ejecuta `conn.execute(query, params)`. |
| `services/db-writer/core/config.py` | `REDIS_URL`, `QUEUE_NAME`, `DUCKDB_PATH`.                       |


**Formato de mensaje esperado:** `{"task_id", "tenant_id", "query", "params"}` (diferente al de `singleton_writer` que usa `{"sql", "db_path"}`).

**Uso:** Pensado para el pipeline `services/api-gateway` → Redis → `services/db-writer`. Si solo usas el agente, el consumidor relevante es `singleton_writer`.

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
| `packages/shared/scripts/duckclaw_setup_wizard.py`    | Wizard CLI: crea `db/<nombre>.duckdb` si no existe.                          |
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

### 3.3 Ejecución del agente (run_sql)

1. El LLM decide usar `run_sql` con una query.
2. `tools.run_sql(db, query)`:
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
| **Re-export compatibilidad**            | `packages/agents/src/duckclaw/api/gateway.py`                                          |
| **Encolar escrituras**                    | `packages/agents/src/duckclaw/forge/homeostasis/singleton_writer.py` (`enqueue_write`) |
| **Consumir cola (agente)**                | `python -m duckclaw.forge.homeostasis.singleton_writer --consume`                      |
| **Consumir cola (api-gateway)**           | `services/db-writer/main.py`                                                           |
| **run_sql**                               | `packages/agents/src/duckclaw/agents/tools.py`                                         |
| **Crear schema**                          | `packages/agents/src/duckclaw/workers/loader.py` (`run_schema`)                        |
| **Schema Finanz**                         | `packages/agents/templates/workers/finanz/schema.sql`                                  |
| **Ruta DB**                               | `packages/agents/src/duckclaw/gateway_db.py`                                           |
| **Sincronizar VPS**                       | `packages/shared/scripts/sync_telegram_duckdb.sh`                                      |
| **Tests pipeline**                        | `tests/run_singleton_writer_pipeline.py`                                               |


