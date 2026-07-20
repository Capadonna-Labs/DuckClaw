# Documentación DuckClaw

Solo contratos y límites de proceso. La implementación vive en el código (`packages/`, `services/`, `uv run duckops --help`).

## Lectura

1. [`GETTING_STARTED.md`](GETTING_STARTED.md) — arranque local
2. [`architecture/system_overview.md`](architecture/system_overview.md) — componentes
3. [`architecture/GATEWAY_DB_WRITER_BOUNDARIES.md`](architecture/GATEWAY_DB_WRITER_BOUNDARIES.md) · [`GATEWAY_PROCESS_BOUNDARIES.md`](architecture/GATEWAY_PROCESS_BOUNDARIES.md)
4. [`architecture/singleton_writer.md`](architecture/singleton_writer.md) · [`api/DB_WRITER_CONTRACT.md`](api/DB_WRITER_CONTRACT.md)
5. [`architecture/tri_cameral_memory.md`](architecture/tri_cameral_memory.md) · [`architecture/MULTI_VAULT_SYSTEM.md`](architecture/MULTI_VAULT_SYSTEM.md)
6. [`api/api_gateway.md`](api/api_gateway.md) · [`api/db_writer.md`](api/db_writer.md)

## Mapa

| Carpeta | Contenido |
|---------|-----------|
| [`architecture/`](architecture/) | Límites gateway/writer, memoria, vaults |
| [`api/`](api/) | Contratos HTTP / colas Redis |

Consola admin: [`apps/duckclaw-admin/README.md`](../apps/duckclaw-admin/README.md).
