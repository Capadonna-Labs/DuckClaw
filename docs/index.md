# DuckClaw — documentación

Plataforma multi-agente · DuckDB · escritor singleton (`services/db-writer`).

| Capa | Dónde |
|------|--------|
| **Especificaciones (SDD)** | [`../specs/`](../specs/) |
| **Mapa del monorepo** | [`../MONOREPO.md`](../MONOREPO.md) |
| **Esta carpeta (`docs/`)** | Runbooks — ver [`DOCUMENTATION_MAP.md`](DOCUMENTATION_MAP.md) |

## Entradas rápidas

| Área | Documento |
|------|-----------|
| Arquitectura | [System overview](architecture/system_overview.md) · [Singleton Writer](architecture/singleton_writer.md) |
| Operación | [COMANDOS](COMANDOS.md) · [Operations](operations/index.md) |
| Diagramas | [Soporte / envíos](diagrams/soporte-envios.md) |
| Agentes (resumen) | [ADF](agents/adf_framework.md) · [Finanz](agents/finanz.md) · [Quant](agents/quant_trader.md) |
| Specs (índice) | [specs/index.md](specs/index.md) |
| API HTTP | [Gateway](api/api_gateway.md) · [DB Writer](api/db_writer.md) |

## Orden de lectura

1. [`MONOREPO.md`](../MONOREPO.md) — qué es `packages/` vs `services/`.
2. `specs/core/` — antes de cambiar gateway o workers.
3. [COMANDOS](COMANDOS.md) — despliegue local.
