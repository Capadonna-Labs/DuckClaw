# DB Writer API Reference

This page has two parts: **write-path contract** (for operators and integrators) and **Python API reference** (mkdocstrings).

## Write-path contract

- **Only** `services/db-writer` should apply durable mutations to DuckDB in production (singleton writer).
- The gateway and agents **enqueue** intents (SQL/state deltas) via Redis; the writer consumes, runs transactional work, and updates task status.
- For HTTP ingress, `POST /api/v1/db/write` on the API Gateway accepts payloads that target a specific `db_path` and `user_id` when using path-aware routing; the writer executes against that path under safety rules.

**Related:**

- [Singleton Writer](../architecture/singleton_writer.md) — architecture contract.
- [Finanz Admin SQL DB-Writer](../specs/finanz_admin_sql_db_writer.md) — spec pointer (canonical file in `specs/features/`).
- [Operations / Commands](../COMANDOS.md) — PM2 and `uv run python services/db-writer/main.py` for local runs.

## Python API reference (mkdocstrings)

## Queue and Task Status Contracts

::: duckclaw.db_write_queue

## Vault/Gateway DB Helpers

::: duckclaw.gateway_db
