# DB Writer (`services/db-writer`)

**Único proceso con permiso de escritura** en DuckDB de producción. Consume cola Redis; transacciones ACID.

```bash
# PM2 / duckops según despliegue local
```

- Código: `main.py`, `quant_state_delta_handler.py`
- Spec: `specs/core/` · Runbook: [`docs/architecture/singleton_writer.md`](../../docs/architecture/singleton_writer.md)
