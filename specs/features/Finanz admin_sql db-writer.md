# Finanz: escrituras locales vía `admin_sql` y db-writer

## Objetivo

El worker **finanz** debe poder cumplir peticiones como «actualizar el saldo de la cuenta Bancolombia a 0 COP» sin inventar restricciones de «solo lectura». Las mutaciones sobre tablas permitidas (`finance_worker.cuentas`, etc.) se ejecutan **solo** a través de la herramienta **`admin_sql`**, que encola SQL hacia el proceso **db-writer** (singleton con bloqueo DuckDB), no mediante `read_sql`.

## Comportamiento

1. **Heurística de primera herramienta** (`packages/agents/src/duckclaw/workers/factory.py`): si el mensaje del usuario, en contexto finanz, parece una **escritura de saldo/cuenta local** (verbos de mutación + saldo/balance o cuenta + entidad bancaria local), el primer turno del agente fuerza **`tool_choice=admin_sql`** (igual que ya se fuerza `read_sql` para «resumen de cuentas»).
2. **Prompt** (`forge/templates/finanz/system_prompt.md`): documenta `admin_sql` para `UPDATE`/`INSERT` sobre filas existentes y prohíbe afirmar bloqueo de escritura sin error real de herramienta.
3. **Allow-list**: sin cambios; sigue `manifest.yaml` → `allowed_tables` y validación en `_admin_sql_worker`.

## Concurrencia DuckDB (gateway + db-writer)

Si el proceso del API Gateway mantiene un `duckdb.connect(..., read_only=True)` abierto al mismo archivo que el db-writer debe mutar, DuckDB puede reportar **Conflicting lock** citando el PID del gateway. Antes de encolar la escritura, `admin_sql` llama a `DuckClaw.suspend_readonly_file_handle()` y tras el poll a `resume_readonly_file_handle()` para liberar el archivo durante la ventana del writer.

## Fuera de alcance

- No se expone SQL arbitrario sin allow-list.
- IBKR y portfolio de bolsa no usan este flujo para saldos de broker (`get_ibkr_portfolio`).
