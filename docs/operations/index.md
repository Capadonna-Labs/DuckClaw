# Operations Docs

Operational runbooks for installing, running, monitoring, and troubleshooting DuckClaw. **Most pages in this section are Spanish-first;** nav labels may be English for consistency with MkDocs.

## Overview (EN)

- Prefer **`uv run …`** from the repository root so the project virtualenv is correct.
- Only **`db-writer`** should perform durable DuckDB writes; gateways and workers stay read-oriented by default.
- Canonical product/architecture truth lives under `specs/` in the repo; these pages are operational glue.

## Resumen (ES)

- Usa siempre **`uv run`** desde la raíz del monorepo para CLI y scripts.
- Las escrituras ACID a DuckDB pasan por el **DB-Writer**; no abrir atajos de escritura desde workers.
- Antes de cambiar comportamiento en producción, revisa **`specs/`** y el [índice de specs en el sitio](../specs/index.md).

## Quick entry / Acceso rápido

| Need | Document |
|------|----------|
| Wizard + topology | [Installation](../Installation.md) |
| Redis, Telegram, PM2, variables (canonical cheat sheet §8) | [Commands (COMANDOS)](../COMANDOS.md) |
| Port / DuckDB / PM2 conflicts | [Troubleshooting Gateway PM2](../Troubleshooting-Gateway-PM2.md) |
| Logs, LangSmith, fly commands | [Observability and Identity](../Observability-2.1-Identidad.md) |
| Sandbox hardening | [Strix Sandbox Security](../Strix-Sandbox-Security.md) |
| Proactive n8n / heartbeat | [Homeostasis Heartbeat](../Homeostasis-Heartbeat.md) |
| The Mind game | [Jugar The Mind](../Jugar-The-Mind.md) |
| Vaults / `/vault` | [Multi Vault System](../Multi-Vault-System.md) |
| Vision (VLM) architecture + env vars | [VLM Integration](../specs/vlm_integration.md) · [COMANDOS §5.2](../COMANDOS.md) |
| Conversation traces / SFT Gemma–MLX | [SFT & conversation traces](../agents/sft_conversation_traces.md) · [COMANDOS §5.3](../COMANDOS.md) |

## Related reading

- **Architecture:** [Singleton Writer](../architecture/singleton_writer.md) · [Tri-Cameral Memory](../architecture/tri_cameral_memory.md) · [Strix Sandbox](../architecture/strix_sandbox.md)
- **Specs:** [Specs hub](../specs/index.md)
- **API (HTTP + Python reference):** [API Gateway](../api/api_gateway.md) · [DB Writer](../api/db_writer.md)

## Operational Guidelines

- Keep `db-writer` as the only write path to protect ACID guarantees and idempotency.
- Treat `specs/` as source of truth before modifying production behaviors.
- Prefer reproducible scripts/commands and record incident learnings in these runbooks.

## Notes

Operational files linked here are part of MkDocs navigation and validated with `mkdocs build --strict`.
