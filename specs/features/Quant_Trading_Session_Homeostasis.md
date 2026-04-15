# Quant: sesión de trading + homeostasis y riesgo

## Alcance

Integrar el marco de homeostasis del worker **Quant-Trader** con el ledger `quant_core.trading_sessions`, objetivos vía `/goals`, límites persistidos en bóveda y enforcement en `propose_trade_signal`.

## Sesión de trading

- Fila singleton `quant_core.trading_sessions.id = 'active'`.
- `session_uid`: UUID único por cada (re)registro de sesión vía `/trading_session`.
- `status`: `ACTIVE` | `PAUSED`. Solo con `ACTIVE` aplica el modo reactor y el bloqueo de riesgo descrito abajo.
- Nueva sesión (`/trading_session` exitoso): se regenera `session_uid` y se reinician `anchor_equity` y `peak_equity` a `NULL` hasta la primera lectura de equity IBKR.

## Drawdown de sesión

- **Pico** (`peak_equity`): máximo `total_value` observado desde el inicio de la sesión ACTIVE actual (actualizado en cada comprobación previa a proponer señal y al registrar sesión si IBKR responde).
- **DD actual**: \((peak\_equity - equity\_now) / peak\_equity\) si `peak_equity > 0`; si no hay pico aún, se usa `equity_now` como primer pico.
- Fuente numérica: mismo contrato que `get_ibkr_portfolio` (`IBKR_PORTFOLIO_API_URL` / `IBKR_PORTFOLIO_API_KEY`), campo `total_value` o `net_liquidation`.

### Política si IBKR no está disponible

Si existe `max_drawdown_pct` en `quant_core.trading_risk_constraints` y la sesión está `ACTIVE`, **`propose_trade_signal` no registra la señal** (fail-closed) cuando no se puede obtener equity, para no operar a ciegas bajo límite declarado.

## `/goals` y worker activo

- El registro de creencias válidas para autocompletar `/goals` viene del **worker activo** del chat (`agent_config.worker_id`), no del primer template con homeostasis del filesystem.
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
- **Fase 2 (parcial)**: `/goals --delta <duración>` programa en `agent_config` (bóveda del usuario) un intervalo; el ticker (`heartbeat` o embebido en el gateway) escanea hub + `db/private/*/*.duckdb` y dispara `[SYSTEM_EVENT]` al worker activo del chat (no `manager`). Ver Fly Commands. Evolución: n8n cron o deduplicación si varios procesos escanean el mismo chat.

## Verificación

- Tests: sorpresa `ceiling`, mirror de goals a `trading_risk_constraints`, bloqueo de `propose_trade_signal` con DD simulado.
- Manual: `/trading_session` → `/goals` (o clave `max_portfolio_drawdown_pct`) → violar DD en paper → `propose_trade_signal` devuelve error `RISK_GOAL_BREACH` o `RISK_EQUITY_UNAVAILABLE`.
