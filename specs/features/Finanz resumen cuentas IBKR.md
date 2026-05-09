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

## Finanz: IBKR solo **live** y aviso sesión Quant **paper**

En el worker **finanz** (manifest `id: finanz`), la herramienta `get_ibkr_portfolio` se sustituye en `packages/agents/src/duckclaw/workers/factory.py` por la variante `replace_get_ibkr_portfolio_with_finanz_live_variant` (`ibkr_bridge.py`):

1. **Un solo GET** con cabecera `X-Duckclaw-IBKR-Account-Mode: live` (cuenta real). **No** hay reintento al modo paper ni uso de `IBKR_ACCOUNT_MODE` para el snapshot en Finanz, para no mezclar cifras de simulación con la cuenta live en el mismo bloque IBKR del resumen.
2. Si en la bóveda Finanz existe `quant_core.trading_sessions` con fila `id = 'active'`, `status = ACTIVE` y `mode = paper`, la salida de la tool **añade** un aviso explícito en español (playbook Quant paper aparte). Si en ese turno Finanz **sí** mostró números IBKR live, el aviso aclara que ese bloque no es el playbook paper; si Finanz **omitió** montos por cuenta paper IBKR, el aviso lo dice (`finanz_active_paper_quant_session_notice`, flag `ibkr_numeric_snapshot_shown`).
3. El modelo debe **reproducir** ese aviso cuando la tool lo incluya y **no** inventar cifras IBKR si la tool indicó modo paper sin saldos.
4. **Cuenta paper en Finanz — sin cifras:** si el modo económico del snapshot es **paper** (inferido por `_ibkr_infer_snapshot_account_mode` o forzado por `IBKR_FINANZ_ASSUMED_SNAPSHOT_MODE=paper`), la tool **no** debe volcar saldos, efectivo ni posiciones; solo un texto que indique que el IB Gateway / snapshot está en **paper**, no **live**, y pasos para ver cuenta real en Finanz. Objetivo: no mezclar montos de simulación en el resumen de cuentas del usuario.
5. **Verdad del snapshot vs cabecera (inferido paper):** cuando el JSON trae señales paper pese a cabecera live, aplica el mismo comportamiento de la viñeta anterior (sin cifras + discrepancia explicada).
6. **Sin metadatos en el JSON:** si el servicio no devuelve modo ni id de cuenta, Finanz no afirma «cuenta real»: la tool puede usar preámbulo **modo no verificado** y entonces **sí** puede incluir números del JSON con advertencia. Override: `IBKR_FINANZ_ASSUMED_SNAPSHOT_MODE=paper|live`. Si el usuario fija `=paper`, aplicar viñeta 4 (sin cifras). La síntesis NL no fuerza «Live» cuando la evidencia es «no verificado»; `finanz_repair_ibkr_tool_live_vs_reply_paper` no reescribe Paper→Live en ese caso. Si la evidencia dice que Finanz **no** muestra saldos IBKR (modo paper), **prohibido** inventar montos del broker.

## Modo paper/live y reintento automático (otros workers)

`packages/agents/src/duckclaw/forge/skills/ibkr_bridge.py` envía `X-Duckclaw-IBKR-Account-Mode` según `IBKR_ACCOUNT_MODE` (por defecto `paper` si el env no está definido). Si la API devuelve `snapshot_unavailable` en ese modo (típico cuando el IB Gateway está solo en **live** y DuckClaw pidió **paper**), el bridge **reintenta una vez** el otro modo (paper o live, el opuesto al configurado) cuando `IBKR_ACCOUNT_MODE_ALT_FALLBACK` no está en `0`/`false`. El preámbulo del tool indica el modo **efectivo** del snapshot y sugiere alinear el env (`IBKR_ACCOUNT_MODE=live`) para evitar el reintento.

**Excepción:** el worker **finanz** usa la variante live-only descrita arriba; no aplica el reintento paper/live de esta subsección a `get_ibkr_portfolio` en Finanz.

Si `IBKR_ACCOUNT_MODE=live` y la API sigue devolviendo `snapshot_unavailable` tras el reintento, el fallo está en el **servicio** que expone `IBKR_PORTFOLIO_API_URL` (p. ej. lectura TWS/API en Capadonna), no en el `.env` del gateway DuckClaw. La respuesta del asistente no debe confundir eso con «gateway desconectado» (error HTTP); ver `system_prompt.md` y el texto de `_extract_portfolio_context` en `ibkr_bridge.py`. En egress Telegram, `finanz_repair_ibkr_snapshot_disconnect_paraphrase` fuerza coherencia si el modelo ignora la tool (ver `worker-telegram-natural-language-egress.md`).

En Capadonna, `snapshot_unavailable` en el JSON de portfolio suele indicar que `get_account_snapshot()` devolvió vacío en el servicio (p. ej. `observability_api`); ver `scripts/deprecated/patch_vps_portfolio_single_snapshot.py` como referencia del contrato en VPS.

### Servicio VPS `observability_api` (puerto típico 8002)

El unit systemd `capadonna-observability` suele fijar `IB_ENV=paper` para procesos locales. Eso **no** debe anular el modo que pide DuckClaw: en el servidor, `GET /api/portfolio/summary` y `GET /api/positions` deben leer la cabecera **`X-Duckclaw-IBKR-Account-Mode`** (`paper` | `live`), elegir el puerto de IB Gateway correspondiente (**4002** paper, **4001** live) y, si el snapshot viene vacío, **reintentar una vez** el modo opuesto (misma idea que `IBKR_ACCOUNT_MODE_ALT_FALLBACK` en el bridge). Opcional: `IBKR_SNAPSHOT_CLIENT_ID` para el `clientId` de la API IB (default `999`).

## Fuera de alcance

- No se añaden nuevas herramientas IBKR distintas de `get_ibkr_portfolio`.
- Errores del gateway IBKR se comunican tal cual al usuario según el prompt existente.
