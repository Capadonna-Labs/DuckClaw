# Tri-Cameral Memory

DuckClaw models memory in three complementary layers:

- **SQL**: deterministic financial/accounting state and operational records.
- **PGQ**: graph-like relationships for multi-hop entity context.
- **VSS**: semantic recall for context injection and retrieval-augmented interactions.

## Design Goals

- Preserve deterministic writes for ledger-critical tasks.
- Support relationship traversal without overloading transactional tables.
- Enable fast semantic recall over contextual artifacts.

## Operational Notes

- Tenant/user vault resolution keeps private and shared scopes separated.
- Semantic context ingestion is asynchronous and queue-backed.
- Worker prompts should treat SQL as hard truth for balances/totals.

## Related specs

- Published hub: [Specs index](../specs/index.md)
- Telegram semantic injection: [Context Injection Telegram](../specs/context_injection_telegram.md)
- Repo canonical (read in Git): `specs/core/02_Analytical_Memory_Architecture.md` — analytical memory architecture.

## Related docs

- [ADF Framework](../agents/adf_framework.md) — how workers use memory and tools
- [Operations hub](../operations/index.md)
