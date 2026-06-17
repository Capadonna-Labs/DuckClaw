# DB-Writer Contract

Contrato canónico del singleton writer (`services/db-writer/`). Gateway, agentes y admin encolan mutaciones; solo este proceso abre DuckDB en `read_only=False` en producción.

## Singleton Writer

- Un único proceso activo por despliegue: PM2 `DuckClaw-DB-Writer` o `python services/db-writer/main.py`.
- Excepción documentada: perfil Spawn con `DUCKCLAW_SPAWN_PROFILE=1` y escrituras inline (`spawn_inline_writes_enabled()`), sin cola Redis. Ver [`SPAWN_GENERIC_DEPLOY.md`](SPAWN_GENERIC_DEPLOY.md).
- Todo el resto del stack (gateway, workers, fly commands) opera `read_only=True` y delega mutaciones vía Redis o comandos tipados.

## Cinco Colas Redis

| Cola (default) | Consumidor | Propósito |
|----------------|------------|-----------|
| `duckdb_write_queue` | `main.execute_write` | Comandos tipados y SQL legacy |
| `duckclaw:state_delta:context` | `context_injection_handler` | `CONTEXT_INJECTION` / semantic memory |
| `duckclaw:state_delta:visual` | `visual_state_delta_handler` | `VISUAL_ASSET_UPSERT` |
| `duckclaw:state_delta:meditate` | `meditate_state_delta_handler` | `PURGE_STALE_TASKS`, `QUARANTINE_MEMORY` |
| `duckclaw:state_delta:reports` | `reports_state_delta_handler` | `CUSTOM_REPORT_UPSERT` |

Nombres overrideables vía env (`DUCKCLAW_*_STATE_DELTA_QUEUE`, `QUEUE_NAME`). El writer hace `BRPOP` en las cinco en paralelo (`asyncio.gather`).

## Ruta Tipada vs Legacy (`raw_sql`)

1. **Tipada (preferida):** payload con `command_type` distinto de vacío. Incluye `raw_sql` registrado en `duckclaw.write_handlers.raw_sql`.
   - `BEGIN TRANSACTION` → dedup ledger → `dispatch_command` → `INSERT admin_write_ledger` → `COMMIT`.
   - Confirmación: `SETEX task_status:<task_id>` (TTL 60s).
2. **Legacy (sin `command_type`):** payload solo con `query` + `params`. Misma transacción + ledger (`command_type=legacy_sql`). Raro en productores nuevos: `enqueue_duckdb_write_sync` reenvía a `RawSqlCommand` tipado.

`RawSqlCommand` (`command_type: raw_sql`) usa el handler tipado y ledger; no cae al path legacy sin `command_type`.

## Ledger e Idempotencia

Capas (de más rápida a durable):

| Capa | Clave / tabla | Comportamiento |
|------|---------------|----------------|
| Redis soft dedup | `dedup:task:{task_id}` | TTL `TASK_STATUS_TTL_SEC * 2`; skip si ya visto |
| Ledger durable | `main.admin_write_ledger` | `task_id` PK; `status='completed'` → skip con `success` |
| Poll caller | `task_status:{task_id}` | JSON `DbWriteTaskStatus` |

Reintentos con el mismo `task_id` son seguros: no duplican efecto si el ledger ya marcó `completed`.

## Dead Letter Queue (DLQ)

Handlers state-delta que fallan tras `BRPOP` encolan en `{source_queue}:dlq` vía `push_dlq` (`db_writer_ops.py`). Payload: `source_queue`, `message`, `error`, `ts`. La cola SQL principal no usa DLQ automática (publica `task_status:failed`).

## Semántica At-Most-Once

- Tras `BRPOP` el mensaje sale de Redis: si el proceso muere antes de `COMMIT`, el write se pierde (no hay requeue).
- Callers que necesitan confirmación deben hacer poll de `task_status:<task_id>` o verificar `admin_write_ledger`.
- `DbPathLockRegistry` serializa escrituras concurrentes al mismo `db_path` normalizado dentro del proceso writer.

## Métricas Redis

Contadores incrementales (`INCRBY`), sin TTL por defecto:

| Clave | Significado |
|-------|-------------|
| `db_writer:metric:processed` | Comandos tipados/SQL completados con éxito |
| `db_writer:metric:failed` | Fallos tipados (handler, ACL, DuckDB) |

`duckops doctor` y admin ops pueden leer `db_writer:metric:processed` como señal de actividad.

## Referencias

- Implementación: `services/db-writer/main.py`, `services/db-writer/db_writer_ops.py`
- Cola shared: `packages/shared/src/duckclaw/db_write_queue.py`
- Arquitectura: [`docs/architecture/singleton_writer.md`](../../../architecture/singleton_writer.md)
- DB-first: [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md)
