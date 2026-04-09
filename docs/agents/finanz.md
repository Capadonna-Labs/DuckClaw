# Finanz Agent

`finanz` is the financial operations worker focused on deterministic account/budget workflows.

## Core Responsibilities

- Register transactions and account updates through approved toolchains.
- Enforce read/write boundaries for SQL operations.
- Summarize contextual financial inputs without fabricating balances.

## Reliability Controls

- Read-only SQL validation for reporting paths.
- Admin SQL routing only for mutation intents.
- Deterministic overrides for sensitive mutation arguments when required.

## Related Specs

- [Finanz admin_sql db-writer](../specs/finanz_admin_sql_db_writer.md)
- [Context Injection (Telegram)](../specs/context_injection_telegram.md)
