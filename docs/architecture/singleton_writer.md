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
