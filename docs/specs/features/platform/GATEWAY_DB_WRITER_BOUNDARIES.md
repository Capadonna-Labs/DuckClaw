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
| `duckclaw:state_delta:meditate` | meditate_state_delta_handler |
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

## Pendiente

- Telegram inbound → cola Redis (fase 2)
- UI Admin: poll genérico `write-tasks` tras mutaciones CRUD
