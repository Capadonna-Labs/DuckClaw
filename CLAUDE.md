# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Setup / run

```bash
bash scripts/bootstrap/up.sh      # macOS/Linux: prereqs + migrate + PM2 + admin
uv run duckops up                 # equivalent, cross-platform
uv run duckops doctor             # diagnose local setup
uv run duckclaw-migrate           # run pending DuckDB migrations
uv run duckops db fresh-dev       # reset to a fresh dev vault
```

Required `.env` vars: `DUCKCLAW_GATEWAY_DB_PATH`, `DUCKCLAW_GATEWAY_URL`, `REDIS_URL`, `DUCKCLAW_ADMIN_API_KEY`, `DUCKCLAW_ADMIN_EMAIL`, `DUCKCLAW_ADMIN_PASSWORD`.

### Admin UI (`apps/duckclaw-admin`, Next.js, port 3001)

```bash
pnpm admin:install       # first time
pnpm admin:dev           # http://localhost:3001
pnpm dev:local           # gateway + db-writer + admin together
pnpm admin:build
pnpm admin:lint
pnpm --dir apps/duckclaw-admin test               # vitest run (all)
pnpm --dir apps/duckclaw-admin test <file-glob>   # single vitest file
```

### Python tests

```bash
uv run pytest tests/ -m "not integration" \
  --ignore tests/run_singleton_writer_pipeline.py \
  --ignore tests/deprecated

uv run pytest tests/test_worker_delegate_invoke.py -k some_test  # single test
```

`-m integration` tests need Redis + the full pipeline running; `slow` and `requires_docker` markers gate other optional suites (see `pyproject.toml`). Guardrail tests worth knowing about: `test_forge_legacy_cleanup.py`, `test_db_first_guardrails_static.py`, `test_schema_migrations.py`, `test_knowledge_sync_queue.py`.

### Full PM2 stack

```bash
uv run duckops stack deploy   # Gateway, DB-Writer, Knowledge-Indexer, Heartbeat
uv run duckops stack up
uv run duckops stack status
```

## Architecture

DuckClaw is a **DB-first, multi-tenant, multi-agent platform** built on generic LangGraph/LangChain — no vertical-specific logic hardcoded in the core Python. Verticals (Quant, PQRSD, Telegram bot, etc.) are opt-in extensions that live outside `packages/agents` core.

### Non-negotiable rule: only DB-Writer writes

DuckDB (`db/private/default/duckclaw.duckdb`) is the control-plane source of truth. The API Gateway, agents, and Knowledge-Indexer always open it `read_only=True`. Every mutation is a **typed Pydantic command** (`duckclaw.write_commands`) → `enqueue_write_command`/`enqueue_typed_command` → Redis queue `duckdb_write_queue` → the singleton **DB-Writer** process, which is the only process allowed ACID writes. Never write to the hub/vault DuckDB file directly from Gateway/agent code, and never poll for a write's completion synchronously inside an HTTP handler (`poll_task_status_sync` with a timeout is forbidden in gateway/indexer hot paths) — admin mutations return `{task_id, accepted}` and the client polls `GET /admin/write-tasks/{task_id}`. Full contract: `docs/api/DB_WRITER_CONTRACT.md`, boundaries: `docs/architecture/GATEWAY_DB_WRITER_BOUNDARIES.md` and `GATEWAY_PROCESS_BOUNDARIES.md`.

Other state-delta Redis queues follow the same fire-and-forget pattern, each with its own DB-Writer handler: `duckclaw:state_delta:{context,visual,vlm,loop,reports}`. RAG folder ingestion is heavier and goes through a separate consumer, `Knowledge-Indexer`, via `duckclaw:knowledge_sync_jobs` (progress reported at `duckclaw:knowledge_sync_status:{job_id}`) — the Gateway only enqueues, never ingests inline.

### Process map

| Process (PM2) | Role | Writes DuckDB? |
|---|---|---|
| `DuckClaw-Gateway` | FastAPI, `/api/v1/admin/*`, chat, enqueues commands | No, `read_only=True` |
| `DuckClaw-DB-Writer` | Consumes `duckdb_write_queue` | Yes — the only regular writer |
| `DuckClaw-Knowledge-Indexer` | Consumes `duckclaw:knowledge_sync_jobs`, scans Obsidian-style vaults | No, enqueues to DB-Writer |
| `DuckClaw-Heartbeat` | Proactive ticks / homeostasis | No, enqueues deltas |
| `duckclaw-admin` | Next.js BFF, proxies to gateway, secrets stay server-side | No |

There is one canonical hub DuckDB file and one schema (`main`, plus DuckDB-internal `information_schema`/`pg_catalog`) — legacy files (`db/duckclaw.duckdb` in repo root, `db/system.duckdb`, `db/telegram.duckdb`, `axis.duckdb`) must not be used. Migrations are sequential and live in `packages/shared/src/duckclaw/schema_migrations.py` (33+ versions); bootstrap DDL in `bootstrap_core.py` is idempotent and never uses `ALTER TABLE ADD COLUMN`.

### Control plane (tables that matter)

Admin identity: `admin_console_users`, `admin_user_profiles`, `admin_user_agents`. Workers: `admin_worker_catalog` + contexts/capabilities/skills/assignments. Policies: `prompt_policy_registry`, `worker_prompt_bindings`, `worker_runtime_policies` (the "airbag" framework has 4 hardcoded fallback policies in `FRAMEWORK_POLICY_PACK`; everything else requires a DB row — avoid adding new `if worker_id == "..."` branches in code, route behavior through these tables instead). Projects: `admin_projects`/`admin_project_agents`. Runtime config (tenant/chat/gateway/LLM/secrets): `admin_runtime_settings`. RAG: `admin_knowledge_sources`/documents/chunks (see `docs/architecture/tri_cameral_memory.md`) — distinct from `main.semantic_memory`, which is context-injection/VLM memory. HITL: `code_decisions`, `agent_uncertainty_log`. Per-user/tenant vaults (SQL+PGQ+VSS "triple memory") are documented in `docs/architecture/MULTI_VAULT_SYSTEM.md` — optional; the hub alone is enough for admin + playground.

### Agents: manager, workers, manifests

`packages/agents/src/duckclaw` implements the LangGraph manager/worker system: `manager/` routes turns to workers by policy/capability, `workers/` builds and runs each worker's graph and tool surface, `forge/` holds RAG and reporting skills, `commands/` is the typed-command layer, `graphs/` are the LangGraph graph definitions.

Every worker has an explicit YAML manifest (`allowed_tables`, `skills`, `forge_context.vault_binding`, and — for delegation — `allowed_delegates`). Tools are granted one at a time; there is no implicit inheritance between agents. Worker-to-worker delegation (`invoke_worker`) is capped at depth 1 (a delegate cannot itself delegate) and is only allowed if the target is listed in the caller's `allowed_delegates`. A per-vault `RLock` (keyed by the resolved DuckDB file path, see `manager/manager_worker_cache.py`) serializes concurrent invokes against the same vault — **be careful here**: if a caller and its delegate resolve to the *same* vault, and the call chain crosses a `ThreadPoolExecutor` thread boundary (as `invoke_worker_graph` in `workers/worker_invoke.py` does for timeout enforcement), a naive re-acquire deadlocks, because `contextvars` do not propagate into `ThreadPoolExecutor` worker threads the way they do for `asyncio` tasks.

### Admin API routers — no god-routers

Routes under `/api/v1/admin` live in `services/api-gateway/routers/admin_domains/*`, one module per domain (e.g. `catalog_skills.py`, `hitl_admin.py`, `kanban.py`, `mcp_connectors.py`, `report_engine.py`). New admin endpoints should get their own domain module rather than growing an existing one into a catch-all router.

### Repo layout

```
duckclaw/
├── packages/
│   ├── shared/     # schema_migrations, write_commands, admin_* readers, knowledge_sync_queue
│   ├── agents/      # manager, workers, forge/rag, commands, MCP bridge
│   ├── core/        # C++ bindings / performance
│   └── duckops/     # CLI: up, init, doctor, stack deploy
├── services/
│   ├── api-gateway/      # FastAPI · admin_domains/* · chat
│   ├── db-writer/        # singleton consumer of duckdb_write_queue
│   ├── knowledge-indexer/  # consumer of duckclaw:knowledge_sync_jobs
│   └── heartbeat/        # proactive ticks
├── apps/duckclaw-admin/  # Next.js BFF (port 3001)
├── harness_core/         # Meditate/homeostasis Python (tables live in main.*, not a separate DuckDB schema)
├── docs/architecture/    # architecture, DuckDB boundaries, service limits
└── tests/                # DB-first guardrail tests
```

### Python entry points

```python
from duckclaw import DuckClaw
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.schema_migrations import run_pending_migrations, verify_migration_integrity
from duckclaw.db_write_queue import enqueue_typed_command
from duckclaw.write_commands import UpsertWorkerCommand, CreateKnowledgeSourceCommand
from duckclaw.workers import WorkerFactory, list_workers
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.forge.rag import build_knowledge_context, search_knowledge
from duckclaw.knowledge_sync_queue import enqueue_knowledge_sync_job, get_job_status
```

## Working style (from `.cursor/rules/`)

- **Lazy senior dev ("ponytail")**: before writing code, check in order — is it needed at all (YAGNI)? does it already exist in this codebase (reuse the helper/pattern)? does stdlib/a platform feature/an already-installed dependency cover it? can it be one line? Only then write the minimum new code. Bug fixes should target the root cause: grep every caller of the function you're touching and fix the shared function once rather than patching only the path a ticket names. No abstractions or boilerplate beyond what was asked for; deletion over addition. A deliberate corner-cut (global lock, O(n²) scan, naive heuristic) gets a `ponytail:` comment naming the ceiling and upgrade path. Exceptions where "lazy" doesn't apply: input validation at trust boundaries, error handling that prevents data loss, security, and anything explicitly requested.
- A **caveman mode** (terse, technical, no filler) is available on request via `/caveman`; code, commits, and PRs are always written normally regardless of that mode.
