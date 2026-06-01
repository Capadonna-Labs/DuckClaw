# Finanz: escrituras locales vía `admin_sql` y db-writer

## Objetivo

El worker **finanz** debe poder cumplir peticiones como «actualizar el saldo de la cuenta Bancolombia a 0 COP» sin inventar restricciones de «solo lectura». Las mutaciones sobre tablas permitidas (`finance_worker.cuentas`, etc.) se ejecutan **solo** a través de la herramienta **`admin_sql`**, que encola SQL hacia el proceso **db-writer** (singleton con bloqueo DuckDB), no mediante `read_sql`.

## Comportamiento

1. **Orquestación declarativa** (`forge/templates/finanz/manifest.yaml` → bloque `tool_orchestration`, spec [WORKER_TOOL_ORCHESTRATION.md](../platform/WORKER_TOOL_ORCHESTRATION.md)): intents `ledger_write` / `ledger_read`, cadenas `get_current_time` → `read_sql`, confirmaciones cortas y replan si falta `admin_sql`. El motor genérico vive en `tool_orchestration.py`; las heurísticas legacy `is_finanz()` en `factory.py` quedan como fallback solo si el manifest no define el bloque.
2. **Prompt** (`forge/templates/finanz/system_prompt.md`): documenta `admin_sql` para `UPDATE`/`INSERT` sobre filas existentes y prohíbe afirmar bloqueo de escritura sin error real de herramienta.
3. **Allow-list**: sin cambios; sigue `manifest.yaml` → `allowed_tables` y validación en `_admin_sql_worker`.

## Concurrencia DuckDB (gateway + db-writer)

Si el proceso del API Gateway mantiene un `duckdb.connect(..., read_only=True)` abierto al mismo archivo que el db-writer debe mutar, DuckDB puede reportar **Conflicting lock** citando el PID del gateway. Antes de encolar la escritura, `admin_sql` llama a `DuckClaw.suspend_readonly_file_handle()` y tras el poll a `resume_readonly_file_handle()` para liberar el archivo durante la ventana del writer.

## Fuera de alcance

- No se expone SQL arbitrario sin allow-list.
- IBKR y portfolio de bolsa no usan este flujo para saldos de broker (`get_ibkr_portfolio`).
