# Tri-Cameral Memory

DuckClaw models memory in three layers:

- **SQL**: deterministic operational / ledger state.
- **PGQ**: graph-like relationships for multi-hop context.
- **VSS**: semantic recall (RAG / context injection).

## Design goals

- Deterministic writes for ledger-critical tasks.
- Relationship traversal without overloading transactional tables.
- Fast semantic recall over contextual artifacts.

## Notes

- Tenant/user vault resolution keeps private and shared scopes separated.
- Semantic ingestion is asynchronous and queue-backed.
- Worker prompts should treat SQL as hard truth for balances/totals.

## Related

- [Multi-vault](MULTI_VAULT_SYSTEM.md)
- [Docs index](../README.md)
