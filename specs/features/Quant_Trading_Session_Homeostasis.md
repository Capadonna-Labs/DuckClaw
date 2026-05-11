# Quant: sesión de trading + homeostasis y riesgo

## Alcance

Integrar el marco de homeostasis del worker **Quant-Trader** con el ledger `quant_core.trading_sessions`, objetivos vía **`/crons`** (alias interno persistente: claves `goals_*` en `agent_config`), límites persistidos en bóveda y enforcement en `propose_trade_signal`.

## Sesión de trading

- Fila singleton `quant_core.trading_sessions.id = 'active'`.
- `session_uid`: UUID único por cada (re)registro de sesión vía `/trading-session`.
- `status`: `ACTIVE` | `PAUSED`. Solo con `ACTIVE` aplica el modo reactor y el bloqueo de riesgo descrito abajo.
- Nueva sesión (`/trading-session` exitoso): se regenera `session_uid` y se reinician `anchor_equity` y `peak_equity` a `NULL` hasta la primera lectura de equity IBKR.

### `/trading-session --status` (snapshots + resumen)

- La serie histórica de PnL en estado del chat (`trading_session_pnl_snapshots_json`) puede ser **v1** (lista numérica legada, sin timestamps) o **v2** (lista de objetos `{"epoch", "pnl"}` ordenada por tiempo) para graficar **eje temporal (UTC)** y tearsheets numéricos a partir solo de los `pnl`. Tras `--status`, las lecturas v1 pueden migrarse en caliente a v2 usando `epoch` reales por append.
- El texto del resumen puede mostrar **equity indicativa** `anchor_equity + PnL` cuando existe `anchor_equity > 0`; si no hay ancla, no se infieren cajas desde `portfolio_positions`.
- La **participación por ticker** se muestra en un **segundo PNG** (torta matplotlib: **top 5** símbolos por peso y rebanada **Otros** con el resto); no hay lista textual de pesos en el mensaje `--status`. Orden de fuentes: nocional **qty×px** en `quant_core.portfolio_positions` para tickers de sesión, con % **normalizados entre tickers de sesión** (suman 100 % entre sí); si no hay nocional útil, **fallback** a **|market_value|** del snapshot IBKR (mismo contrato que `get_ibkr_portfolio`) restringido a tickers de sesión, con % = **|mv| / `total_value` de la cuenta** (mismo criterio que el resumen de posiciones vs cuenta; la torta usa ángulos proporcionales al |mv| y **etiquetas** con ese %); si no hay `total_value` usable, se usa como denominador la suma de |mv| en tickers de sesión; si tampoco aplica, **reparto igual** entre tickers de sesión.
- Las figuras outbound del fly-command se envían como **FIFO** (primero tearsheet PnL/DD, con panel PnL anotado Actual y Máx/Mín cuando aplica; luego la torta) vía cola por `chat_id` en el api-gateway/Telegram.

## Drawdown de sesión

- **Pico** (`peak_equity`): máximo `total_value` observado desde el inicio de la sesión ACTIVE actual (actualizado en cada comprobación previa a proponer señal y al registrar sesión si IBKR responde).
- **DD actual**: \((peak\_equity - equity\_now) / peak\_equity\) si `peak_equity > 0`; si no hay pico aún, se usa `equity_now` como primer pico.
- Fuente numérica: mismo contrato que `get_ibkr_portfolio` (`IBKR_PORTFOLIO_API_URL` / `IBKR_PORTFOLIO_API_KEY`), campo `total_value` o `net_liquidation`.

### Política si IBKR no está disponible

Si existe `max_drawdown_pct` en `quant_core.trading_risk_constraints` y la sesión está `ACTIVE`, **`propose_trade_signal` no registra la señal** (fail-closed) cuando no se puede obtener equity, para no operar a ciegas bajo límite declarado.

## `/crons` y worker activo

- El registro de creencias válidas para autocompletar **`/crons`** viene del **worker activo** del chat (`agent_config.worker_id`), no del primer template con homeostasis del filesystem.
- Objetivos se guardan en el estado del chat (misma DuckDB que el fly command: bóveda del usuario en gateways dedicados).

## `quant_core.trading_risk_constraints`

- Singleton `id = 'active'`.
- `max_drawdown_pct`: techo de DD permitido (0–1, ej. `0.05` = 5%).
- Se actualiza al añadir un goal cuyo `belief_key` sea `max_portfolio_drawdown_pct` (template Quant + NL normalizado).

## Homeostasis: comparación `ceiling`

- Para `max_portfolio_drawdown_pct`, la creencia usa `comparison: ceiling` en YAML.
- Anomalía si `observed > target + threshold` (DD observado por encima del máximo permitido más banda de advertencia).

## Proactividad

- **Fase 1 (implementada)**: en cada turno del grafo Quant, si `status = ACTIVE`, se inyecta un bloque de contexto en el system prompt (tickers, `session_uid`, modo, límite DD si existe) e instrucciones para evaluar mercado y proponer señal cuando elriesgo lo permita.
- **Fase 2 (parcial)**: `/crons --delta <duración>` programa en `agent_config` (bóveda del usuario) un intervalo; el ticker (`heartbeat` o embebido en el gateway) escanea hub + `db/private/*/*.duckdb` y dispara `[SYSTEM_EVENT]` al worker activo del chat (no `manager`). Ver Fly Commands. Evolución: n8n cron o deduplicación si varios procesos escanean el mismo chat.

## Verificación

- Tests: sorpresa `ceiling`, mirror de goals a `trading_risk_constraints`, bloqueo de `propose_trade_signal` con DD simulado.
- Manual: `/trading-session` → `/crons` (o clave `max_portfolio_drawdown_pct`) → violar DD en paper → `propose_trade_signal` devuelve error `RISK_GOAL_BREACH` o `RISK_EQUITY_UNAVAILABLE`.
