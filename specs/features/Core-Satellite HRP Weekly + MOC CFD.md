# Core-Satellite: HRP semanal + MOC CFD (Quant Trader)

## Objetivo

Dos pipelines operativos desacoplados:

1. **HRP semanal (contenedor)**: recomputación semanal de pesos jerárquicos con covarianza Ledoit-Wolf, tope 40 % por activo y persistencia en `quant_core.hrp_mandates`.
2. **MOC CFD (válvula intradía)**: fusionar mandato HRP vigente con fase CFD (`quant_core.fluid_state.phase`) para proponer señales batch HITL (`strategy_name = moc_hrp_cfd`) y ejecutarlas con `/execute_all_moc`.

## Variables de entorno

| Variable | Uso |
|----------|-----|
| `HRP_CORE_SATELLITE_UNIVERSE` | Lista CSV de tickers (ej. `SPY,QQQ,IEFA`). Obligatorio en jobs. |
| `DUCKCLAW_QUANT_SCRIPT_DB` | Ruta DuckDB vault (jobs). |
| `REDIS_URL` / `DUCKCLAW_REDIS_URL` | Cola singleton (`enqueue_duckdb_write_sync`). |
| `TZ=America/Bogota` | PM2/cron COT recomendado. |
| `DUCKCLAW_QUANT_ALERT_CHAT_ID` | Telegram `chat_id` para alertas MOC/HRP vía `N8N_OUTBOUND_WEBHOOK_URL`. Opcional si no hay n8n. |
| IBKR/Gateway existentes | `IBKR_GATEWAY_OHLCV_URL`, lake, etc. como en spec Capadonna. |
| `DUCKCLAW_MOC_MACRO_VSS` | `1` = válvula MOC v2 con régimen PGQ + perfil VSS (véase spec macro). |
| `DUCKCLAW_MOC_VSS_TIMEOUT_SEC` | Timeout lectura VSS en el job MOC (default `3`). |
| `DUCKCLAW_MOC_PROFILE_LLM` | `1` opcional para parse LLM del perfil. |
| `DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW` | Franja **HH:MM[:SS]-HH:MM[:SS]** en **America/Bogota** **lun–vie** (inclusiva en inicio y fin; segundos opcionales, p. ej. `14:40-14:55` o `14:40:00-14:59:30`). **(a)** `propose_trade_signal` con `strategy_name` distinto de `moc_hrp_cfd` **solo** crea filas Ledger dentro de esta ventana (fuera → `OUTSIDE_MOC_PREP_WINDOW`). **(b)** Con `DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS=1`, la auto-exec encadenada a `execute_approved_signal` también exige esta ventana. Default **`14:40:00-14:59:30`**. |
| `DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES` | **`1`** omite **(a)** y **(b)** respecto del horario MOC (solo dev/CI; evitar en prod). |
| `DUCKCLAW_QUANT_AUTO_EXECUTE_IGNORE_MOC_WINDOW` | Alias legacy de **`DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES`** (`1` = mismo efecto). |

**Macro PGQ + perfil:** [MOC Macro PGQ VSS.md](./MOC%20Macro%20PGQ%20VSS.md).

Restricción: **no** ejecutar HRP intradía automáticamente; solo cron dominical (`0 20 * * 0` COT PM2 ejemplo) o manual.

## Ventana operativa de referencia (America/Bogota) vs MOC PM2

**Ventana día “mercado” referencia para equities (Quant / objetivo overnight_gap_squeeze):** **08:30–15:00 COT**, para decidir cuándo el worker debe ingestar/actuar sobre OHLCV y CFD en tiempo de sesión habitual (referencia Nasdaq; no sustituye el calendario de feriados ni la apertura real del venue).

**Dentro de 08:30–15:00 COT (lun–vie operativo):**

- Sesión Telegram con `session_goal.objective=overnight_gap_squeeze`: **antes** del tramo MOC típico es **solo preparación** (ingestas OHLCv/portfolio/CFD, sandbox, lectura DuckDB): **no** llamar `propose_trade_signal` para `cfd_auto` u otras hasta la ventana MOC configurada — la herramienta devuelve `OUTSIDE_MOC_PREP_WINDOW`; las señales batch del PM2 siguen siendo `moc_hrp_cfd`. No **reemplazar** el job [`moc_pipeline.py`](scripts/quant/moc_pipeline.py).
- No usar sólo timestamps de última fila en `quant_core.ohlcv_data` como “hora local del trader” sin `get_current_time` o caveat explícito.

**Ventana típica MOC en host (lun–vie, COT según cron PM2 ejemplo):**

- Crons de referencia: ~**14:40** calc, ~**14:50** remind, ~**14:55** expire (véase tabla más abajo). La ventana **ejecutable/propose** en gateway default se extiende hasta **14:59:30** COT para capturar cola de cierre; alinear env con ops si el PM2 difiere.
- En esa franja las señales `strategy_name=moc_hrp_cfd` generadas/expiradas por el pipeline tienen **autoridad**: el tick proactivo de Telegram (`TRADING_TICK` / `/goals`) **no** debe contradictor ellas ni duplicar un segundo flujo propio “MOC” al mismo efecto.

**Ejecución batch tras MOC:** ver sección `/execute_all_moc` más abajo.

**Alerta temprana empresa (opcional mismo turno que HRP):** si el playbook cuantitativo lo exige, consultar [FMP earnings calendario y transcripts](./Integración%20FMP%20earnings%20calendario%20y%20transcripts%20(read-only).md) antes de asumir sizes agresivos cercanos a reportes; no contradice evidencia OHLCV ni el pipeline MOC.

## Singleton writer

Todas las mutaciones en vault desde jobs: [`enqueue_duckdb_write_sync`](packages/shared/src/duckclaw/db_write_queue.py), sin `duckdb.connect(...).execute` mutador en proceso del script salvo `:memory:` en tests.

## Evidencia OHLCV antes de `propose_trade_signal`

Los jobs establecen `bind_quant_market_evidence_chat("__moc__")` / `"__hrp_weekly__"` y tras cada ingesta OK `note_quant_market_evidence_ticker(ticker)` (véase `quant_tool_context`).

## HRP weekly (`scripts/quant/hrp_weekly_job.py`)

1. Ingesta `_fetch_ib_gateway_ohlcv_impl` por ticker: `timeframe=1d`, `lookback_days=120`.
2. Si **cualquier** ticker tiene `COUNT(*) < 60` en `quant_core.ohlcv_data` para ese ticker en la ventana usada → **STOP**, no UPSERT mandates, warning en `task_audit_log`.
3. Sandbox PyPortfolioOpt: retornos `pct_change().dropna()`, `CovarianceShrinkage(returns).ledoit_wolf()`, `HRPOpt(returns=returns, cov_matrix=S).optimize()`, cap 40 % y renormalizar.
4. UPSERT `quant_core.hrp_mandates`; `valid_until = computed_at + 7 days`.
5. Telegram resumen si chat_id + webhook configurados.

## MOC pipeline (`scripts/quant/moc_pipeline.py`)

Env `MOC_PHASE=calc|remind|expire`.

**Crons** (lun–vie ejemplo, servidor en `America/Bogota`): 14:40 calc, 14:50 remind, 14:55 expire.

### Fase calc

1. Mandatos vigentes: `hrp_mandates` con `valid_until > now()`, última fila por ticker (`computed_at`).
2. Si vacío → alerta Telegram + auditoría “mandates expired”.
3. Equity desde `_get_ibkr_portfolio_impl`: `total_value` o `net_liquidation`. Si **equity &lt; 10000 USD** → STOP y mensaje **Capital insuficiente para operar HRP-CFD**.
4. Por ticker: fase CFD = último `quant_core.fluid_state.phase` orden `timestamp DESC LIMIT 1`. Sin historia → **`SOLID`** (válvula 0.4).
5. Si `DUCKCLAW_MOC_MACRO_VSS=1`: una vez por ciclo — `detect_current_regime`, `get_investor_profile` (timeouts VSS); por ticker — `calculate_target_allocation_v2`. Si no — `calculate_target_allocation` (átomo legacy): válvulas GAS/LIQUID/SOLID/PLASMA.
6. `action != HOLD` → `_propose_trade_signal_impl(..., proposed_weight = target_weight*100, strategy_name=moc_hrp_cfd)`. Con `strategy_name=moc_hrp_cfd` **no** aplica auto-ejecución aunque `DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS=1`.

**Otras estrategias** (`overnight_gap_squeeze`, `cfd_auto`, etc.): `propose_trade_signal` está **bloqueado** fuera de la ventana MOC (misma env que auto-exec) salvo bypass dev; la **propuesta** de Ledger no aparece antes del tramo MOC (`OUTSIDE_MOC_PREP_WINDOW`). Con `DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS=1`, la cadena hasta `execute_approved_signal` **también** exige esa ventana.
7. Persistir estado del ciclo (`MOC_SESSION_UID` UUID en archivo bajo `$TMPDIR`/`.duckclaw_moc_session` o env para fases siguientes).

### Fase remind

Si hay `PENDING_HITL` con `strategy_name=moc_hrp_cfd` y `session_uid` del ciclo guardado → recordatorio Telegram.

### Fase expire

`UPDATE quant_core.trade_signals SET status='EXPIRED', updated_at=now()` donde `strategy_name=moc_hrp_cfd`, `status='PENDING_HITL'` y edad desde `ts` &gt; 15 minutos. Notificación con conteo expirado.

## `/execute_all_moc <session_uid>`

Comando fly: aprueba en bloque tras `grant_execute_order` por señal y `_execute_approved_signal_impl` secuencial.

## DDL

Ver `packages/agents/.../Quant-Trader/schema.sql`: `quant_core.hrp_mandates`, columnas extra `quant_core.session_ticks` (`moc_executed`, `moc_notional`, `moc_n_orders`).

## Estado delta

`TradeSignalMutation.strategy_name`; db-writer escribe ese valor en `quant_core.trade_signals` en lugar del literal `cfd_auto`.
