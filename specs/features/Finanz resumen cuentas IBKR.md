# Finanz: resumen de cuentas locales + IBKR

## Objetivo

Cuando el usuario pide un **resumen amplio** de cuentas o saldos almacenados en DuckDB (`finance_worker.cuentas`, etc.), el worker **finanz** debe incorporar también el contexto del **broker IBKR** en el mismo análisis, siempre que la skill IBKR esté activa en el manifest y existan credenciales (`IBKR_PORTFOLIO_API_URL` / `IBKR_PORTFOLIO_API_KEY` u equivalentes documentados).

## Comportamiento

1. **Primera herramienta** (`packages/agents/src/duckclaw/workers/factory.py`): el texto del usuario que coincide con `_is_finanz_local_accounts_query` sigue forzando **`read_sql`** en el primer turno del agente (heurística `force_finanz_cuentas`). Lo mismo aplica a **`_is_finanz_debts_query`** / `force_finanz_deudas` (`finance_worker.deudas`) y **`_is_finanz_budgets_query`** / `force_finanz_presupuestos` (`finance_worker.presupuestos`), para no sintetizar montos o meses desde el historial del chat. Si `agent_node.heuristic_first_tool` es falso, esas tres heurísticas **no** se anulan al limpiar `force_read_sql`.
2. **Segunda herramienta**: si el último mensaje en el estado es un **`ToolMessage`** de **`read_sql`** y el último **`HumanMessage`** cumple `_is_finanz_local_accounts_query`, y aún no hubo **`get_ibkr_portfolio`** después de ese humano, el siguiente turno del agente fuerza **`tool_choice=get_ibkr_portfolio`** (`_finanz_should_force_ibkr_after_local_cuentas_read`).
3. **Exclusiones**: no aplica si el mensaje humano contiene **`[SYSTEM_DIRECTIVE:`** (flujos `/context`). No aplica si el texto menciona explícitamente IBKR/bolsa/portfolio en el sentido de excluir el patrón local (la heurística local ya filtra esas subcadenas). Si **`get_ibkr_portfolio`** no está en el catálogo de tools (skill IBKR desactivada), solo se ejecuta `read_sql`.

## Totales (resumen / estatus amplio)

En peticiones de **resumen**, **estado** o **estatus** de cuentas **sin** filtrar un solo banco, la respuesta debe incluir:

1. **Subtotal por moneda** sobre las filas de `finance_worker.cuentas` obtenidas vía `read_sql` en ese turno (sumar `balance` agrupando por `currency`).
2. **Bloque IBKR** aparte (totales en la divisa que devuelva `get_ibkr_portfolio`), sin fusionar COP + USD en una cifra única sin tipo de cambio en evidencia.

Prompt: `system_prompt.md` (MANDATO DE FRESCURA). Síntesis NL: regla adicional en `user_reply_nl_synthesis.synthesize_user_visible_reply` cuando `worker_id` es `finanz`.

## Prompt

`packages/agents/src/duckclaw/forge/templates/finanz/system_prompt.md` alinea el MANDATO DE FRESCURA y la sección IBKR con este flujo de dos pasos y los totales anteriores.

## Esquema SQL local (deudas y presupuestos)

El modelo no debe asumir columnas inexistentes (evita errores Binder en DuckDB):

- **`finance_worker.deudas`:** `id`, `description`, `amount`, `creditor`, `due_date`, `created_at` (sin `status`). Para totales narrativos, no duplicar suma si coexisten fila resumen de contrato y cuotas mensuales del mismo crédito.
- **`finance_worker.presupuestos`:** `category_id`, `amount`, `year`, `month` (sin `category` / `budget_amount`); nombre vía `JOIN finance_worker.categories`.

Texto operativo: mismas viñetas en `system_prompt.md` (sección gastos/cuentas locales).

## Deduplicación de totales (Mac Mini agregado + cuotas)

Cuando `read_sql` sobre `finance_worker.deudas` devuelve JSON de filas y el worker es **finanz**, `packages/agents/src/duckclaw/workers/read_pool.py` puede envolver la salida en `{ "deudas_filas": [...], "_totales_resumen_cop": { ... } }` si detecta fila agregada TC Bancolombia / Mac Mini con cuotas mensuales duplicadas. El modelo debe usar `total_recomendado_resumen_cop` como total único en COP (ver `system_prompt.md`).

## Fuera de alcance

- No se añaden nuevas herramientas IBKR distintas de `get_ibkr_portfolio`.
- Errores del gateway IBKR se comunican tal cual al usuario según el prompt existente.
