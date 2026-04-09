# Finanz: escrituras locales vía `admin_sql` y db-writer

## Objetivo

El worker **finanz** debe poder cumplir peticiones como «actualizar el saldo de la cuenta Bancolombia a 0 COP» sin inventar restricciones de «solo lectura». Las mutaciones sobre tablas permitidas (`finance_worker.cuentas`, etc.) se ejecutan **solo** a través de la herramienta **`admin_sql`**, que encola SQL hacia el proceso **db-writer** (singleton con bloqueo DuckDB), no mediante `read_sql`.

## Comportamiento

1. **Heurística de primera herramienta** (`packages/agents/src/duckclaw/workers/factory.py`): si el mensaje del usuario, en contexto finanz, parece una **escritura de saldo/cuenta local** (verbos de mutación + saldo/balance o cuenta + entidad bancaria local), o **registro de gasto** (`registra/registrar` + «gasto»), o **ajuste de presupuesto/efectivo** («resta/restar» + presupuesto/efectivo/categoría), el primer turno del agente fuerza **`tool_choice=admin_sql`** (igual que ya se fuerza `read_sql` para «resumen de cuentas»). En esos mismos casos, el bind genérico del LLM **omite `get_ibkr_portfolio`**, **`fetch_market_data`** y **`fetch_lake_ohlcv`** para evitar bucles locales ↔ IBKR y llamadas espurias a ingesta de mercado/CFD cuando la intención es solo DuckDB local (siguen disponibles cuando el usuario pide portfolio, velas OHLCV o mercado explícitamente; las rutas forzadas por heurística OHLCV no usan ese bind recortado).
2. **Anclaje por turno** (`_finanz_local_mutation_anchor_message`): cuando la misma heurística detecta mutación local y no hay directiva de resumen de contexto, el gateway inserta un `SystemMessage` con **`[FINANZ_LOCAL_MUTATION_ANCHOR]`** **inmediatamente después** del bloque inicial de system prompts y **antes** de los turnos Human/Assistant/Tool, para no romper el contrato tool-use (un `system` al final del historial, tras `ToolMessage`, puede hacer que el proveedor ignore salidas de herramienta y repetir llamadas). El ancla repite el texto del usuario y obliga coherencia de monto, descripción, categoría, cuenta y mes/año del presupuesto.
3. **Override determinístico (gasto local):** si el mensaje del usuario incluye un monto en forma «Nk» (p. ej. `6k` → 6000 COP) y la heurística de mutación local aplica, `tools_node` reescribe los argumentos de **`insert_transaction`** y el SQL de **`admin_sql`** antes de ejecutar: monto alineado al texto, `category_id` de **Recreacion** cuando el usuario menciona recreación (resuelto vía `categories`), sustitución de `50000` espuria en `UPDATE`, y `presupuestos` con **año/mes actuales** (`strftime` sobre `CURRENT_DATE`) en lugar de fechas inventadas.
4. **Presupuesto mensual sin fila previa:** cuando llega un `UPDATE finance_worker.presupuestos` para gasto local de recreación, el gateway puede reescribir a `INSERT ... ON CONFLICT(category_id, year, month) DO UPDATE` para que el descuento se aplique aunque la fila del mes aún no exista (evita reportar “actualizado” con 0 filas afectadas).
5. **Prompt** (`forge/templates/finanz/system_prompt.md`): documenta `admin_sql` para `UPDATE`/`INSERT` sobre filas existentes, el bloque `FINANZ_LOCAL_MUTATION_ANCHOR` cuando aplique, y prohíbe afirmar bloqueo de escritura sin error real de herramienta.
6. **Allow-list**: sin cambios; sigue `manifest.yaml` → `allowed_tables` y validación en `_admin_sql_worker`.

## Concurrencia DuckDB (gateway + db-writer)

Si el proceso del API Gateway mantiene un `duckdb.connect(..., read_only=True)` abierto al mismo archivo que el db-writer debe mutar, DuckDB puede reportar **Conflicting lock** citando el PID del gateway. Antes de encolar la escritura, `admin_sql` llama a `DuckClaw.suspend_readonly_file_handle()` y tras el poll a `resume_readonly_file_handle()` para liberar el archivo durante la ventana del writer.

## Fuera de alcance

- No se expone SQL arbitrario sin allow-list.
- IBKR y portfolio de bolsa no usan este flujo para saldos de broker (`get_ibkr_portfolio`).

## Contrato `finance_worker.transactions`

Los modelos no deben inventar columnas: la tabla tiene `id` (PK, asignada por la tool `insert_transaction` o explícita en `admin_sql`), `amount`, `description`, `category_id`, `tx_date` (no `category`, `account`, `currency`, `transaction_date`). Ajuste de saldo en cuentas locales vía `UPDATE` sobre `finance_worker.cuentas`; presupuesto vía `finance_worker.presupuestos`. Detalle en `forge/templates/finanz/system_prompt.md`.
