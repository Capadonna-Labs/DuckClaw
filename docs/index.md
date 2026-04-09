# DuckClaw Documentation

DuckClaw is a multi-agent platform with a zero-trust posture, state isolation by tenant/user, and a strict separation between compute and mutation.

## Core Principles

- Zero-Trust execution across gateway, workers, and external integrations.
- Specs-Driven Development: implementation follows `specs/` as source of truth.
- Singleton mutation path: only DB-Writer mutates DuckDB state.
- Tri-cameral memory model for operational and semantic workloads.

## Documentation Map

- **Architecture**: ACID mutation contracts, memory model, and sandbox boundaries.
- **Agents**: Agent Definition Framework (ADF), worker templates, and role-specific docs.
- **Specs**: curated links to product/architecture specs.
- **API**: auto-generated Python API docs via `mkdocstrings`.

## Local Usage

```bash
mkdocs serve
```

Build static site:

```bash
mkdocs build --strict
```
