# Singleton Writer Contract

**`services/db-writer`** is the only component allowed to write DuckDB state.

## Why

- ACID transaction boundaries for all state deltas.
- No race conditions across concurrent chat/tool executions.
- Centralized idempotency, retries, and audit status.

## Write flow

1. Gateway/agents enqueue a validated write intent (typed command or compat SQL).
2. Redis holds the queue.
3. `db-writer` consumes, runs transactional writes, publishes task status.

## Boundaries

- Gateway and workers are read-oriented by default.
- Any new mutation path must go through the singleton writer.

## Related

- [`../api/DB_WRITER_CONTRACT.md`](../api/DB_WRITER_CONTRACT.md)
- [`GATEWAY_DB_WRITER_BOUNDARIES.md`](GATEWAY_DB_WRITER_BOUNDARIES.md)
- [`../GETTING_STARTED.md`](../GETTING_STARTED.md)
