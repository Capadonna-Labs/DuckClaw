# DuckClaw Documentation

DuckClaw is a multi-agent platform with a zero-trust posture, state isolation by tenant/user, and a strict separation between compute and mutation.

**Language / Idioma:** Architecture and product docs are mostly English; operational runbooks are primarily Spanish (ES), with English (EN) navigation labels where useful. Search is configured for both `en` and `es`.

## Quick Start

Run the docs locally from the repository root:

```bash
uv run mkdocs serve
```

Build a production-ready static site with strict validation:

```bash
uv run mkdocs build --strict
```

## Core Principles

- Zero-Trust execution across gateway, workers, and external integrations.
- Specs-Driven Development: implementation follows `specs/` as source of truth.
- Singleton mutation path: only DB-Writer mutates DuckDB state.
- Tri-cameral memory model for operational and semantic workloads.

## Documentation Map

| Area | What you get | Entry |
|------|----------------|-------|
| **Architecture** | ACID mutation contracts, memory model, sandbox boundaries | [Singleton Writer](architecture/singleton_writer.md), [Tri-Cameral Memory](architecture/tri_cameral_memory.md), [Strix Sandbox](architecture/strix_sandbox.md) |
| **Agents** | ADF, worker templates, role-specific guides, SFT trace pipeline | [ADF Framework](agents/adf_framework.md), [Finanz](agents/finanz.md), [Quant Trader](agents/quant_trader.md), [SFT & conversation traces](agents/sft_conversation_traces.md) |
| **Specs** | Curated spec hub + links to canonical files in the repo | [Specs index](specs/index.md) |
| **API** | **HTTP:** FastAPI routes and behavior (overview in API pages). **Python:** module reference via `mkdocstrings` | [API Gateway](api/api_gateway.md), [DB Writer](api/db_writer.md) |
| **Operations** | Install, commands, troubleshooting, observability | [Operations hub](operations/index.md) |

## Suggested Reading Order

1. [Architecture](architecture/singleton_writer.md) — system boundaries and invariants.
2. [Specs](specs/index.md) — before changing services or agents.
3. [API](api/api_gateway.md) — HTTP surface + Python reference sections.
4. [Operations](operations/index.md) — deploy, troubleshoot, incidents.

## Resumen (ES)

- **Arquitectura:** contrato singleton writer, memoria tri-cameral, sandbox Strix.
- **Especificaciones:** ver [índice de specs](specs/index.md); la fuente canónica sigue en `specs/features/` y `specs/core/` del repo.
- **API:** las páginas bajo `API` mezclan **visión HTTP** (rutas FastAPI) y **referencia Python** generada con mkdocstrings.
- **Operaciones:** [instalación, comandos y runbooks](operations/index.md) (principalmente en español); variables VLM y trazas en [COMANDOS](COMANDOS.md) §5.2–5.3.
