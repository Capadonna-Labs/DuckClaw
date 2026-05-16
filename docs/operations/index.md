# Operaciones

Runbooks en español/inglés mixto. **Normativa:** [`../../specs/`](../../specs/).

## Acceso rápido

| Necesidad | Documento |
|-----------|-----------|
| Wizard + topología | [Installation](../Installation.md) |
| PM2, Redis, Telegram, variables | [COMANDOS](../COMANDOS.md) |
| Conflictos puerto / DuckDB / PM2 | [Troubleshooting Gateway PM2](../Troubleshooting-Gateway-PM2.md) |
| Logs, LangSmith, fly commands | [Observability](../Observability-2.1-Identidad.md) |
| Sandbox Strix | [Strix Sandbox Security](../Strix-Sandbox-Security.md) |
| Heartbeat | [Homeostasis Heartbeat](../Homeostasis-Heartbeat.md) |
| Multi-vault `/vault` | [Multi Vault System](../Multi-Vault-System.md) |
| Trazas SFT | [SFT traces](../agents/sft_conversation_traces.md) · `packages/agents/train/README.md` |
| VLM | `specs/features/VLM INTEGRATION.md` · COMANDOS §5.2 |

## Principios

- Solo **db-writer** escribe DuckDB en producción.
- Cambios de comportamiento: leer `specs/` primero.
- Usar `uv run` desde la raíz del monorepo.

## Arquitectura y API

- [Singleton Writer](../architecture/singleton_writer.md) · [Tri-cameral](../architecture/tri_cameral_memory.md)
- [API Gateway](../api/api_gateway.md) · [DB Writer](../api/db_writer.md)
- [Índice specs](../specs/index.md)
