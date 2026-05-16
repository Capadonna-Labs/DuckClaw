# DB Writer

Implementación: `services/db-writer/`.

## Contrato

- **Único** proceso con escritura durable a DuckDB en producción.
- Gateway y workers **encolan** por Redis (`duckclaw.db_write_queue` en shared).
- El writer ejecuta en transacción y actualiza estado de tarea.

## HTTP relacionado

`POST /api/v1/db/write` en el gateway acepta payloads con `db_path` / `user_id` según despliegue.

## Python (shared)

- Cola: `duckclaw.db_write_queue`
- Rutas gateway: `duckclaw.gateway_db`

## Ver también

- [Singleton Writer](../architecture/singleton_writer.md)
- [COMANDOS](../COMANDOS.md) — PM2 y `uv run python services/db-writer/main.py`
- Spec: `specs/features/Finanz admin_sql db-writer.md`
