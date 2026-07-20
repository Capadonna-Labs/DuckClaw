# Singleton Writer Contract

DuckClaw enforces a single mutation path: **`services/db-writer`** is the only component allowed to write DuckDB state.

## Why It Exists

- Guarantees ACID transaction boundaries for all state deltas.
- Reduces race conditions across concurrent chat/tool executions.
- Centralizes idempotency, retries, and audit status updates.

## Write Flow

1. Gateway/agents generate a validated state delta or SQL write intent.
2. Intent is enqueued in Redis.
3. `db-writer` consumes the queue, runs transactional writes, and publishes task status.

## Scope Boundaries

- Gateway and workers are read-oriented by default.
- Write permissions are not distributed to template workers.
- Any new mutation path must remain compatible with the singleton contract.

## Related docs

- Core infra: [`../core/01_System_Infrastructure.md`](../core/01_System_Infrastructure.md)
- DB-first: [`DB_FIRST_CORE_REFACTOR.md`](DB_FIRST_CORE_REFACTOR.md)
- Contrato cola/ledger: [`../api/DB_WRITER_CONTRACT.md`](../api/DB_WRITER_CONTRACT.md)

## Related operations

- [Operations hub](../operations/index.md)
- [Getting started](../GETTING_STARTED.md) — Redis queues, DB-Writer PM2
- [DB Writer API (HTTP + Python)](../api/db_writer.md)
