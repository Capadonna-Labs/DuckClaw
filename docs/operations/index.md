# Operaciones

Runbooks en español/inglés mixto. **Normativa:** [`../specs/`](../specs/) (bajo `docs/specs/`, no en la raíz del repo).

## Acceso rápido

| Necesidad | Documento |
|-----------|-----------|
| Wizard + topología | [`README.md`](../README.md) (quick start) · [`COMANDOS.md`](../COMANDOS.md) |
| PM2, Redis, Telegram, variables | [COMANDOS](../COMANDOS.md) |
| Conflictos puerto / DuckDB / PM2 | [COMANDOS](../COMANDOS.md) · `uv run python scripts/doctor.py` |
| Logs, LangSmith, fly commands | [Observability](Observability-2.1-Identidad.md) |
| Sandbox Strix | [Skills & sandbox Strix](../core/03_Skills_and_Tooling_Framework.md) (§ Sandbox de ejecución) |
| Heartbeat | [Homeostasis Heartbeat](Homeostasis-Heartbeat.md) |
| Meditate / Harness Core | [Meditate Homeostasis](Meditate-Homeostasis.md) |
| Multi-vault `/vault` | [Multi Vault System](Multi-Vault-System.md) |
| Trazas SFT | [SFT traces](../agents/sft_conversation_traces.md) · `packages/agents/train/` · `uv run duckops train` |

## Principios

- Solo **db-writer** escribe DuckDB en producción.
- Cambios de comportamiento: leer `docs/specs/` primero.
- Usar `uv run` desde la raíz del monorepo.

## Arquitectura y API

- [DB-first Core Refactor](../specs/features/platform/DB_FIRST_CORE_REFACTOR.md) · [Singleton Writer](../architecture/singleton_writer.md) · [Tri-cameral](../architecture/tri_cameral_memory.md)
- [API Gateway](../api/api_gateway.md) · [DB Writer](../api/db_writer.md)
- [Specs plataforma (índice)](../specs/features/platform/README.md)
