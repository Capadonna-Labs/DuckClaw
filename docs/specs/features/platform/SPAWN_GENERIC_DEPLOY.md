# Spawn — despliegue genérico DuckClaw (VM)

**Estado:** implemented (instalador + bootstrap `--core-only` + ecosystem spawn)  
**Relacionado:** [DUCKCLAW_ADMIN_UI.md](DUCKCLAW_ADMIN_UI.md), [DOTENV_SINGLE_SOURCE.md](DOTENV_SINGLE_SOURCE.md), fork [OpenRouterLabs/spawn](https://github.com/OpenRouterLabs/spawn)

## Objetivo

Proveer un harness de agentes **local-first**, **agnóstico de dominio** y desatendido, instalable con:

```bash
spawn duckclaw <cloud>
```

La VM ejecuta [`scripts/deploy/spawn-install.sh`](../../../scripts/deploy/spawn-install.sh) tras clonar el repo. No se inyectan esquemas `quant_core`, `finance_worker`, `pqrsd_crm` ni `run_schema` de templates industriales en el día cero.

## Contrato `.env` (VM)

Spawn (o el operador) escribe en la raíz del monorepo:

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `OPENROUTER_API_KEY` | Sí | LLM vía OpenRouter |
| `DUCKCLAW_ADMIN_API_KEY` | Sí | Clave compartida gateway ↔ admin BFF |
| `DUCKDB_PATH` | Sí | Hub DuckDB, p. ej. `db/private/default/duckclaw.duckdb` |
| `DUCKCLAW_DB_PATH` | Alias | Misma ruta que `DUCKDB_PATH` (compat wizard/scripts) |
| `REDIS_URL` | Sí | p. ej. `redis://127.0.0.1:6379/0` (redis-server vía systemd) |
| `DUCKCLAW_SPAWN_PROFILE` | No | `1` activa checks opcionales en `doctor.py` |
| `DUCKCLAW_REPO_ROOT` | No | Ruta absoluta al clone (PM2 / scripts) |

**No** definir en perfil spawn: `DUCKCLAW_FINANZ_DB_PATH`, `DUCKCLAW_QUANT_TRADER_DB_PATH`, multiplex Telegram, etc.

Plantilla: [`config/.env.spawn.example`](../../../config/.env.spawn.example).

## Fases del instalador

1. **Preflight:** SWAP 2GB si RAM &lt; 4GB.
2. **OS deps:** `build-essential`, `git`, `curl`, `python3-venv`, `redis-server`, Node 20, PM2 global, `uv`.
3. **Python:** `uv sync` en la raíz del monorepo.
4. **Bootstrap:** `uv run duckops db bootstrap --core-only --only <DUCKDB_PATH>` (síncrono, antes de PM2; wrapper compatible: `scripts/bootstrap_dbs.py`).
5. **Admin UI:** `pnpm install` + `pnpm build` en `apps/duckclaw-admin`; `.env.local` con gateway URL y admin key.
6. **PM2:** `config/ecosystem.spawn.config.cjs` → Gateway `:8000`, Admin `:3000`.

## Tablas core-only (`--core-only`)

| Tabla / schema | Uso |
|----------------|-----|
| `agent_config` | `/model`, equipo, sandbox por chat |
| `api_conversation` | Historial admin/API |
| `telegram_conversation` | Memoria Telegram (sin prefijo `main.`) |
| `task_audit_log` | Auditoría de tareas |
| `main.authorized_users` | Whitelist Telegram |
| `main.user_shared_db_access` | Grants shared DB |
| `main.admin_console_users` | Login consola web |
| `main.semantic_memory` | RAG / admin memory |
| `system.duckdb` registry | vía `ensure_registry()` |

**Excluido:** `quant_core`, `pqrsd_crm`, `finance_worker`, `war_room_core`, `run_schema` de templates forge.

## Stack PM2 (perfil mínimo)

| Proceso | Puerto | Notas |
|---------|--------|--------|
| `DuckClaw-Gateway` | 8000 | FastAPI |
| `duckclaw-admin-ui` | 3000 | Next.js producción |

**Fuera de PM2 (perfil mínimo):** `DuckClaw-DB-Writer` — ver [Cola huérfana](#cola-huérfana-redis-sin-db-writer).

**Redis:** `systemctl` — requerido por el gateway en arranque (caché, no colas de escritura obligatorias en spawn).

## Cola huérfana (Redis sin DB-Writer)

Si el gateway o el grafo abren DuckDB en **solo lectura** y mutan vía Redis (`duckdb_write_queue`, `duckclaw:state_delta:*`), los mensajes **no se consumen** sin `DuckClaw-DB-Writer` y los datos quedan acumulados en Redis.

Con `DUCKCLAW_SPAWN_PROFILE=1` (y sin `DUCKCLAW_SPAWN_USE_DB_WRITER=1`):

| Componente | Comportamiento |
|------------|----------------|
| `graph_server._invoke_ephemeral_gateway_graph` | Hub DuckDB **RW** (`read_only=False`) cuando no hay vault separado |
| `enqueue_duckdb_write_sync` | `apply_duckdb_write_sync` en proceso (+ `task_status` en Redis para polls) |
| `push_context_injection_delta_redis` / `push_visual_state_delta_sync` | Handlers db-writer inline vía `spawn_inline_delta` |
| Admin playground (misma ruta que hub) | `DuckClaw` RW |

**No definir en `.env` spawn** (forzarían RO o multiplex industrial):

- `DUCKCLAW_GATEWAY_READ_ONLY`, `*_READ_ONLY` en rutas gateway
- `DUCKCLAW_FINANZ_DB_PATH`, `DUCKCLAW_QUANT_TRADER_DB_PATH`, etc. (priorizan otro hub y rompen mono-usuario)

Escape hatch: `DUCKCLAW_SPAWN_USE_DB_WRITER=1` + PM2 `ecosystem.db-writer.config.cjs` restaura cola + proceso writer.

Código: [`spawn_profile.py`](../../../packages/shared/src/duckclaw/spawn_profile.py), [`db_write_queue.py`](../../../packages/shared/src/duckclaw/db_write_queue.py).

## Integración Spawn (fork)

- Agente `duckclaw` en `manifest.json`.
- `SPAWN_DUCKCLAW_REPO` default: `https://github.com/Arevalojj2020/duckclaw.git`.
- Override: `spawn duckclaw hetzner --repo <url>`.

## Validación post-install

```bash
duckdb db/private/default/duckclaw.duckdb -c \
  "SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ('quant_core','pqrsd_crm','finance_worker');"
# 0 filas

curl -s http://127.0.0.1:8000/health
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/
```

## Referencias código

- [`packages/shared/src/duckclaw/bootstrap_core.py`](../../../packages/shared/src/duckclaw/bootstrap_core.py)
- `uv run duckops db bootstrap` / [`scripts/bootstrap_dbs.py`](../../../scripts/bootstrap_dbs.py) (`--core-only`)
- [`scripts/deploy/spawn-install.sh`](../../../scripts/deploy/spawn-install.sh)
- [`config/ecosystem.spawn.config.cjs`](../../../config/ecosystem.spawn.config.cjs)
