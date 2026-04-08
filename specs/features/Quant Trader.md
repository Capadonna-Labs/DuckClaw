# Quant Trader




### Objetivo
Orquestar la ejecución táctica cuantitativa y generación de señales de trading bajo un entorno Zero-Trust. El worker **Quant Trader** actúa como ejecutor aislado, delegando el análisis macro a `Finanz`, procesando backtesting exclusivamente dentro del Strix Sandbox, y requiriendo autorización explícita (HITL) para cualquier mutación de estado en el broker (IBKR).

### Contexto
- **Orquestación:** Invocado vía Manager Handoff (UX: "A2A Contract") tras un intent emitido por `Finanz` o el usuario.
- **Aislamiento:** `network_access: false`. Comunicación externa restringida a MCP Servers (IBKR, Strix Sandbox).
- **Entorno de Ejecución:** `IBKR_ACCOUNT_MODE=paper` inyectado por el harness.
- **Cómputo:** Prohibida la ejecución de código en el host. Todo script (Pandas, NumPy, TA-Lib) corre en contenedores efímeros OrbStack.

### Esquema de datos
Tablas en DuckDB (`db/private/<chat_id>/quant_ledger.db`), mutadas exclusivamente vía `StateDelta` a Redis (Singleton Writer):

```sql
CREATE TABLE finance_worker.trading_mandates (
    mandate_id UUID PRIMARY KEY,
    source_worker VARCHAR, -- ej. 'finanz'
    asset_class VARCHAR,
    direction VARCHAR, -- 'LONG', 'SHORT', 'NEUTRAL'
    max_weight_pctDECIMAL(5,2),
    status VARCHAR, -- 'PENDING', 'ANALYZING', 'FULFILLED', 'REJECTED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE finance_worker.trade_signals (
    signal_id UUID PRIMARY KEY,
    mandate_id UUID REFERENCES finance_worker.trading_mandates(mandate_id),
    ticker VARCHAR,
    signal_type VARCHAR, -- 'ENTRY', 'EXIT'
    proposed_weight DECIMAL(5,2),
    sandbox_backtest_cid VARCHAR, -- Hash del log en Strix
    human_approved BOOLEAN DEFAULT FALSE,
    status VARCHAR, -- 'AWAITING_HITL', 'EXECUTED', 'DISCARDED'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Flujo Cognitivo
1. **Ingesta de Mandato:** Recibe el payload del Manager con el contexto del mandato de `Finanz`.
2. **Recolección de Evidencia:** Ejecuta `fetch_market_data` vía IBKR MCP para obtener OHLCV intradía/histórico.
3. **Cuantificación Aislada:** Genera script de Python (estrategia, cálculo de z-score, reversión a la media) y lo envía a `execute_sandbox_script`.
4. **Síntesis y Propuesta:** Analiza el `stdout` (JSON) del Sandbox. Si la señal es positiva, invoca `propose_trade_signal`.
5. **Intercepción RiskGuard:** El nodo determinista (Python) intercepta la propuesta, calcula el valor nominal contra el saldo líquido en DuckDB, y emite el `StateDelta`.
6. **Pausa HITL:** El worker suspende ejecución y emite webhook a Telegram: *"Señal {signal_id} lista. Requiere `/execute_signal {signal_id}`"*.
7. **Ejecución:** Tras el comando del usuario, el Manager reactiva al worker para invocar `execute_approved_signal`.

### Contratos (Skills)
- `fetch_market_data(ticker: str, timeframe: str) -> dict`: Retorna OHLCV. Sujeto a Regla de Evidencia Única.
- `execute_sandbox_script(code: str, dependencies: list[str]) -> dict`: Ejecuta lógica quant en Strix. Retorna `stdout` sanitizado. Timeout estricto: 30s.
- `propose_trade_signal(mandate_id: str, ticker: str, weight: float, rationale: str) -> dict`: Emite intent de señal. Dispara el RiskGuard determinista.
- `execute_approved_signal(signal_id: str) -> dict`: Envía la orden al IBKR MCP. Falla determinísticamente si `human_approved != TRUE` en DuckDB.

### Validaciones
- **Regla de Evidencia Única:** El nodo Validator rechaza cualquier `propose_trade_signal` si no existe un registro de `fetch_market_data` exitoso para el mismo `ticker` en el turno actual del LangGraph state.
- **RiskGuard Determinista:** Si `proposed_weight` > límite global del tenant (ej. 10% del capital líquido), el nodo Python sobrescribe el peso al máximo permitido antes de persistir en DuckDB, notificando la reducción en el rationale.
- **Domain Closure:** El worker rechazará responder a preguntas macroeconómicas o de sentimiento de mercado, indicando que su dominio es estrictamente ejecución cuantitativa y derivando el intent a `Finanz`.

### Edge cases
- **Ceguera Sensorial (IBKR Down/Rate Limit):** Si `fetch_market_data` falla, el worker aborta el pipeline inmediatamente con el payload: *"🔴 Ceguera Sensorial: Imposible validar OHLCV para {ticker}. Mandato suspendido."* No se permite fallback a Tavily ni extrapolación de datos.
- **Sandbox OOM / Timeout:** Si el script de backtesting excede memoria o tiempo en OrbStack, el worker reporta el fallo técnico y marca el mandato como `REJECTED` por inviabilidad computacional.
- **HITL Timeout:** Si el usuario no ejecuta `/execute_signal` en un plazo de 4 horas (configurable por tenant), un cronjob del Singleton Writer marca la señal como `DISCARDED` (Stale Signal) para evitar ejecuciones con datos de mercado caducados.
- **Manager Routing Failure:** Si el payload del "A2A Contract" llega malformado, el worker emite un log a `task_audit_log` y solicita retransmisión al Manager sin mutar el ledger.