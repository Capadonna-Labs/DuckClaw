# Gateway ↔ DB-Writer Boundaries

Complementa `GATEWAY_PROCESS_BOUNDARIES.md` (RAG/Indexer) y `DB_WRITER_CONTRACT.md` (colas SQL).

## Principio

**Gateway = encola y responde al instante.** **DB-Writer = único RW ACID** sobre DuckDB hub/vault.

## Gateway (HTTP)

| Permitido | Prohibido |
|-----------|-----------|
| `open_gateway_db(read_only=True)` | `read_only=False` en PM2 (guardrails) |
| `enqueue_admin_command` / `enqueue_typed_command` | `poll_task_status_sync` en handlers HTTP |
| `GET /admin/write-tasks/{task_id}` | Esperar db-writer dentro del request |
| `run_heavy_work` para lecturas pesadas | DDL/bootstrap hub en lifespan |

## DB-Writer (PM2)

| Cola | Handler |
|------|---------|
| `duckdb_write_queue` | Typed commands + ledger |
| `duckclaw:state_delta:context` | context_injection_handler |
| `duckclaw:state_delta:visual` | visual_state_delta_handler |
| `duckclaw:state_delta:vlm` | vlm_state_delta_handler |
| `duckclaw:state_delta:loop` | loop_state_delta_handler |
| `duckclaw:state_delta:meditate` | loop_state_delta_handler (legacy queue) |
| `duckclaw:state_delta:reports` | reports_state_delta_handler |

**Startup:** `startup_bootstrap.py` — DDL usage tables + `seed_catalog_if_empty` (cold start hub).

## Admin async writes

```http
POST /api/v1/admin/...  → { "task_id": "...", "accepted": true }
GET  /api/v1/admin/write-tasks/{task_id}  → { "status": "pending"|"success"|"failed" }
```

Patrón idéntico a jobs RAG (`GET /admin/knowledge/jobs/{job_id}`).

## Spawn profile (dev)

Con `DUCKCLAW_SPAWN_PROFILE=1`, el Gateway puede aplicar writes inline — excepción documentada, no stack PM2 producción.

## Agents (fly commands + knowledge indexer)

| Ruta | Patrón |
|------|--------|
| `duckclaw.db_write_fire_and_forget.enqueue_write_command` | Encola typed command; **no** bloquea |
| `wait_write_task` / `DUCKCLAW_WRITE_POLL_SEC` | Poll opcional (default **0** en gateway) |
| `knowledge_auto_sync._enqueue_knowledge_command` | Fire-and-forget; falla solo si Redis/enqueue lanza |
| `commands/chat_state`, `crons`, `team_access` | Encolan vía helper; mensaje `Write encolado (task_id=…)` sin poll |

**Prohibido en hot paths gateway/indexer:** `poll_task_status_sync` con timeout > 0 salvo `DUCKCLAW_WRITE_POLL_SEC` explícito (spawn/dev).

## Pendiente

- Telegram inbound → cola Redis (fase 2)
- UI Admin: poll genérico `write-tasks` tras mutaciones CRUD largas

## Agents (fly / indexer)

`duckclaw.db_write_fire_and_forget` — sin poll por defecto (`DUCKCLAW_WRITE_POLL_SEC=0`):
`chat_state`, `crons`, `team_access`, `knowledge_auto_sync`, `history`, `runtime_toggles`, `team_templates`, `llm_usage_log`, `media_usage_log`, `model_setup`, HITL services, report/update prompt bridges.

## Write-task detail

db-writer publica `detail` en Redis para `sync_catalog_prompts` y `restore_framework_policy_pack` (vía `write_task_detail.py`).

## Métricas Overview

`GET /admin/health` expone `gateway_metrics.db_write_queue_depth` (LLEN `duckdb_write_queue`) junto a RAG y RAM. La consola Overview permite refresh manual con bypass de caché (45s TTL en store).

`gateway_metrics.pm2_processes` lista estado PM2 (`online` / `stopped` / `missing`) y RAM (`monit.memory` → `rss_mb`, heap Node vía `axm_monitor` si existe) para `DuckClaw-Gateway`, `DuckClaw-DB-Writer`, `DuckClaw-Knowledge-Indexer` y `DuckClaw-Heartbeat`. La recolección usa `pm2 jlist` con timeout **2s**; si PM2 no está en PATH, la clave es `[]` y el endpoint no bloquea. Overview muestra DB-Writer, Indexer y Heartbeat en una fila compacta bajo el encabezado del stack.

## Liberación de recursos (Gateway in-process)

```http
POST /api/v1/admin/gateway/release-worker-cache
→ { entries_before, entries_after, rss_mb_before, rss_mb_after, worker_graph_cache }
```

- Solo vacía caché LangGraph + `gc.collect()` en el proceso HTTP actual.
- **No** reinicia PM2 ni DB-Writer.
- UI: botón en tarjeta «Caché workers» con modal de confirmación (coste: cold start en próximo chat).
- Misma rutina que fly commands (`duckclaw.ops.gateway_resource_release`).
