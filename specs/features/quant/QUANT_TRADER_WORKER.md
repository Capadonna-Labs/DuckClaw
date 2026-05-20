# Quant Trader




### Objetivo
Orquestar la ejecución táctica cuantitativa y generación de señales de trading bajo un entorno Zero-Trust. El worker **Quant Trader** actúa como ejecutor aislado; puede ofrecer **síntesis macro y de sentimiento** acotada (herramientas web/Reddit/FMP + vínculo a tickers/sesión) sin sustituir OHLCV para propuestas. El backtesting corre en Strix Sandbox; toda orden al broker exige autorización explícita (HITL). Con `COMFYUI_API_URL` y `comfyui.enabled` en el manifest, acepta pedidos explícitos de **generación de imágenes** vía `generate_visual_asset` / `edit_visual_asset` (ComfyUI Visual Bridge).

### Contexto
- **Orquestación:** Invocado vía Manager Handoff (UX: "A2A Contract") tras un intent del usuario u otro worker (p. ej. `Finanz`).
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
1. **Ingesta de Mandato:** Recibe el payload del Manager (mandato previo o pedido directo del usuario).
2. **Recolección de Evidencia:** Ejecuta `fetch_market_data` vía IBKR MCP para obtener OHLCV intradía/histórico.
3. **Cuantificación Aislada:** Genera script de Python (estrategia, cálculo de z-score, reversión a la media) y lo envía a `execute_sandbox_script`.
4. **Síntesis y Propuesta:** Analiza el `stdout` (JSON) del Sandbox. Si la señal es positiva, invoca `propose_trade_signal`.
5. **Intercepción RiskGuard:** El nodo determinista (Python) intercepta la propuesta, calcula el valor nominal contra el saldo líquido en DuckDB, y emite el `StateDelta`.
6. **Pausa HITL:** El worker suspende ejecución y emite webhook a Telegram: *"Señal {signal_id} lista. Requiere `/execute-signal {signal_id}`"*.
7. **Ejecución:** Tras el comando del usuario, el Manager reactiva al worker para invocar `execute_approved_signal`.

### Contratos (Skills)
- `fetch_market_data(ticker: str, timeframe: str) -> dict`: Retorna OHLCV. Sujeto a Regla de Evidencia Única.
- `execute_sandbox_script(code: str, dependencies: list[str]) -> dict`: Ejecuta lógica quant en Strix. Retorna `stdout` sanitizado. Timeout efectivo según [`security_policy.yaml`](packages/agents/src/duckclaw/forge/templates/Quant-Trader/security_policy.yaml) del worker.
- `propose_trade_signal(mandate_id: str, ticker: str, weight: float, rationale: str) -> dict`: Emite intent de señal. Dispara el RiskGuard determinista.
- `execute_approved_signal(signal_id: str) -> dict`: Envía la orden al IBKR MCP. Falla determinísticamente si `human_approved != TRUE` en DuckDB.

### ML4T (sandbox + batch, sin ml4t-data)

- La imagen DuckClaw `docker/sandbox` incluye **`ml4t-diagnostic[backtest]`** (métricas y librería `ml4t.backtest`). **No** se integra **`ml4t-data`**; la serie de precios sigue entrando por **`fetch_market_data`**, **`fetch_ib_gateway_ohlcv`** y **`read_sql`** contra Duck gestionado por DuckClaw.
- **Sandbox Quant (Telegram):** red **`deny`** por defecto; solo computar sobre OHLCV/arrays inyectados por el host o ficheros montados RO.
- Jobs **batch offline** (`network none`): `scripts/quant/run_ml4t_batch_docker.sh` monta DuckDB solo lectura y corre diagnósticos / resumen vectorial sobre `quant_core.ohlcv_data`; documentado en [`docs/COMANDOS.md`](docs/COMANDOS.md).
- **`ml4t.diagnostic.integration.DataQualityReport`:** en Telegram/sandbox debe armarse mediante la plantilla `packages/agents/src/duckclaw/forge/templates/Quant-Trader/snippets/ml4t_dqr_from_ohlcv_sandbox.py` sobre filas OHLC vigentes (`read_sql`/`fetch_*` mismo turno), no mediante dict incompleto: el contrato ML4T exige `symbol`, `source`, `frequency`, `date_range` (UTC), métricas anidadas y `DataAnomaly` bien tipados — de lo contrario pydantic lanza errores de validación (p. ej. «6 validation errors for DataQualityReport»).

### Validaciones
- **Regla de Evidencia Única:** El Validator rechaza `propose_trade_signal` si no hubo **`fetch_market_data` *o*** **`fetch_ib_gateway_ohlcv` exitoso** para el mismo `ticker` en el turno actual (véase mensaje tool `EVIDENCE_UNIQUE_RULE` en código).
- **RiskGuard Determinista:** Si `proposed_weight` > límite global del tenant (ej. 10% del capital líquido), el nodo Python sobrescribe el peso al máximo permitido antes de persistir en DuckDB, notificando la reducción en el rationale.
- **Domain Closure:** La ejecución y las señales siguen ancladas a evidencia OHLCV/portfolio. Preguntas o contexto sobre macro/sentimiento se responden **dentro del worker** con herramientas permitidas (p. ej. búsqueda web, Reddit, calendarios FMP), sin usar narrativa como sustituto de velas para `propose_trade_signal`.

### Edge cases
- **Ceguera Sensorial:** Si falla la ingesta OHLCV necesaria en ese paso, la respuesta al usuario sigue la línea **canónica del template Quant-Trader (Caveman / harness):** `🔴 Ceguera Sensorial:[herramienta] no retornó datos. STOP.` — sin párrafos extra. **Prohibido** usar Tavily (u otras fuentes web) como sustituto de precios u OHLCV. Sustituir `[herramienta]` por el nombre exacto de la tool que falló.
- **Sandbox OOM / Timeout:** Si el script de backtesting excede memoria o tiempo en OrbStack, el worker reporta el fallo técnico y marca el mandato como `REJECTED` por inviabilidad computacional.
- **HITL Timeout:** Si el usuario no ejecuta `/execute-signal` en un plazo de 4 horas (configurable por tenant), un cronjob del Singleton Writer marca la señal como `DISCARDED` (Stale Signal) para evitar ejecuciones con datos de mercado caducados.
- **Manager Routing Failure:** Si el payload del "A2A Contract" llega malformado, el worker emite un log a `task_audit_log` y solicita retransmisión al Manager sin mutar el ledger.