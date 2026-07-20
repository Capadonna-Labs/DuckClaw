# Operaciones

Runbooks de operación del stack. Arquitectura y contratos: [`../architecture/`](../architecture/) · [`../api/`](../api/).

## Índice

| Tema | Doc |
|------|-----|
| Wizard + topología | [`../GETTING_STARTED.md`](../GETTING_STARTED.md) · [`../README.md`](../README.md) |
| Diagnóstico | `uv run duckops doctor` |
| Multi-vault | [`../architecture/MULTI_VAULT_SYSTEM.md`](../architecture/MULTI_VAULT_SYSTEM.md) |
| Telegram | [`TELEGRAM.md`](TELEGRAM.md) |
| Heartbeat / loop / meditate | [`Homeostasis-Heartbeat.md`](Homeostasis-Heartbeat.md) · [`Loop-Homeostasis.md`](Loop-Homeostasis.md) · [`Meditate-Homeostasis.md`](Meditate-Homeostasis.md) |

## Antes de cambiar comportamiento

- Límites gateway/writer: [`../architecture/GATEWAY_PROCESS_BOUNDARIES.md`](../architecture/GATEWAY_PROCESS_BOUNDARIES.md)
- DB-first: [`../architecture/DB_FIRST_CORE_REFACTOR.md`](../architecture/DB_FIRST_CORE_REFACTOR.md) · [Singleton Writer](../architecture/singleton_writer.md) · [Tri-cameral](../architecture/tri_cameral_memory.md)
