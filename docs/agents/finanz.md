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

## Specs (canónico en repo)

- `specs/features/finanz/FINANZ_ADMIN_SQL_DB_WRITER.md`
- `specs/features/finanz/FINANZ_CONTEXT_INJECTION_TELEGRAM.md`
- Plantilla: `packages/agents/src/duckclaw/forge/templates/finanz/`
