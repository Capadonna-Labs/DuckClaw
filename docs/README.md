# Documentación DuckClaw

Mapa de `docs/` — solo arquitectura, framework, DuckDB y servicios.

## Lectura recomendada

1. [`GETTING_STARTED.md`](GETTING_STARTED.md) — arranque local (`duckops up` / `stack deploy`)
2. [`architecture/system_overview.md`](architecture/system_overview.md) — componentes
3. [`architecture/DB_FIRST_CORE_REFACTOR.md`](architecture/DB_FIRST_CORE_REFACTOR.md) — DB-first, qué es core
4. [`architecture/tri_cameral_memory.md`](architecture/tri_cameral_memory.md) — SQL + PGQ + VSS
5. [`api/DB_WRITER_CONTRACT.md`](api/DB_WRITER_CONTRACT.md) + [`api/db_writer.md`](api/db_writer.md) — escrituras DuckDB
6. [`api/api_gateway.md`](api/api_gateway.md) — gateway HTTP
7. [`core/`](core/) — infra, skills, agentes, flujo de datos
8. [`operations/`](operations/) — heartbeat, loop, Telegram, multi-vault (ver también `architecture/MULTI_VAULT_SYSTEM.md`)

## Mapa

| Carpeta | Contenido |
|---------|-----------|
| [`architecture/`](architecture/) | Visión del sistema, límites gateway/writer, memoria, vaults, Tailscale, UI patterns admin |
| [`core/`](core/) | Capas del framework (skills, sandbox, memoria analítica, lógica agéntica) |
| [`api/`](api/) | Contratos gateway y db-writer |
| [`operations/`](operations/) | Runbooks de operación (homeostasis, Telegram) |

## Notas

- **`harness_core/`** (raíz del repo) es runtime activo de `/loop` (homeostasis), no legacy.
- Train: CLI `uv run duckops train` — no hay API admin `/train`.
- Consola admin: [`apps/duckclaw-admin/README.md`](../apps/duckclaw-admin/README.md) y [`apps/duckclaw-admin/docs/`](../apps/duckclaw-admin/docs/).
