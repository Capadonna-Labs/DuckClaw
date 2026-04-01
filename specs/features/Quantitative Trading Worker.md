# Quantitative Trading Worker

**Objetivo**
Desplegar un Agente Soberano de Trading Cuantitativo capaz de ingerir series temporales financieras, ejecutar *backtesting* y análisis técnico en aislamiento (Strix Sandbox), y proponer o ejecutar órdenes de mercado bajo un modelo estricto de *Human-in-the-Loop* y Zero-Trust.

**Contexto**
El agente operará sobre el esquema `quant_core` en DuckDB. Utilizará un servidor MCP para conectarse a brokers (ej. Interactive Brokers / Alpaca) para extraer datos OHLCV (Open, High, Low, Close, Volume). Todo el cálculo matemático pesado (Pandas, NumPy, TA-Lib) se delega al Strix Sandbox para proteger el Event Loop de LangGraph y el KV Cache del Mac mini. Las órdenes de compra/venta se emiten como `StateDelta` hacia el Singleton Writer.

**Implementación en el monorepo:** La primera entrega integra `quant_core` y las skills (`fetch_market_data`, `propose_trade`, `execute_order`, validación de precios, `/execute_signal`) en el **template Finanz** ([packages/agents/src/duckclaw/forge/templates/finanz](packages/agents/src/duckclaw/forge/templates/finanz)), misma bóveda `.duckdb` que finanzas personales. La ingesta OHLCV usa HTTP (`IBKR_MARKET_DATA_URL`) alineado con el bridge existente de portafolio; MCP puede sustituir o complementar ese endpoint en una fase posterior.

**Esquema de Datos (`quant_core.duckdb`)**
```sql
CREATE SCHEMA quant_core;

-- Capa Bronze: Series temporales crudas
CREATE TABLE quant_core.ohlcv_data (
    ticker VARCHAR,
    timestamp TIMESTAMP,
    open DOUBLE,
    high DOUBLE,
    low DOUBLE,
    close DOUBLE,
    volume DOUBLE,
    PRIMARY KEY (ticker, timestamp)
);

-- Capa Silver: Señales generadas por el Sandbox
CREATE TABLE quant_core.trade_signals (
    signal_id UUID PRIMARY KEY,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ticker VARCHAR,
    strategy_name VARCHAR,
    action VARCHAR, -- 'BUY', 'SELL', 'HOLD'
    confidence_score DOUBLE,
    target_price DOUBLE,
    stop_loss DOUBLE
);

-- Capa Gold: Estado del Portafolio y Ejecución
CREATE TABLE quant_core.portfolio_positions (
    ticker VARCHAR PRIMARY KEY,
    qty DOUBLE,
    avg_entry_price DOUBLE,
    current_price DOUBLE,
    unrealized_pnl DOUBLE,
    updated_at TIMESTAMP
);
```

**Flujo Cognitivo (Pipeline Cuantitativo)**
1. **Ingesta (Trigger):** El agente recibe un cron o petición en Telegram (`"Analiza NVDA"`). Usa la skill `fetch_market_data` (vía MCP) para actualizar `quant_core.ohlcv_data`.
2. **Análisis Aislado (Strix Sandbox):** El agente genera un script de Python que lee los datos de DuckDB (`read_only=True`), calcula indicadores técnicos (RSI, MACD, Bandas de Bollinger), genera un gráfico de velas (`.png`) y emite un JSON con las señales de trading.
3. **Síntesis y Riesgo:** El LLM lee el JSON resultante del Sandbox y lo cruza con las reglas de gestión de riesgo del `domain_closure.md` (ej. *Position Sizing* máximo del 5% del portafolio).
4. **Mutación de Estado:** Si hay una señal válida, el agente emite un `StateDelta` al Singleton Writer para insertar el registro en `quant_core.trade_signals`.
5. **Egress (Human-in-the-Loop):** Envía el gráfico generado y la propuesta de trade a Telegram. **El agente se detiene aquí.** Espera un comando explícito del usuario (ej. `/execute signal_id`) para llamar a la API del broker.

**Contratos (Skills)**
*   `fetch_market_data(ticker: str, timeframe: str, lookback_days: int)`: Llama al MCP del broker, extrae OHLCV y hace el `INSERT OR IGNORE` en DuckDB.
*   `run_quant_sandbox(script: str)`: Ejecuta Python aislado. Tiene preinstalados `pandas`, `numpy`, `mplfinance`, `ta-lib`. Retorna JSON y guarda gráficos en `/workspace/output/`.
*   `propose_trade(ticker: str, action: str, qty: float, limit_price: float, stop_loss: float)`: Emite el `StateDelta` a la tabla `trade_signals`.
*   `execute_order(signal_id: str)`: Skill bloqueada por política. Solo ejecutable si el `trace_id` actual proviene de una confirmación explícita del usuario en Telegram.

**Validaciones (Domain Closure & Validator Node)**
*   **Zero-Hallucination de Precios:** El nodo `Validator` intercepta cualquier mensaje saliente. Si el agente menciona un precio actual para un ticker, el validador hace un `SELECT close FROM quant_core.ohlcv_data WHERE ticker = ? ORDER BY timestamp DESC LIMIT 1`. Si el precio difiere en más de un 0.1%, la respuesta es rechazada.
*   **Límites de Riesgo (Hardcoded):** Prohibido proponer operaciones en corto (Short Selling) o usar apalancamiento (Margin) a menos que el `manifest.yaml` lo habilite explícitamente con `risk_level: aggressive`.
*   **Aislamiento de Capital:** El agente solo puede leer el saldo de la cuenta de "Paper Trading" o el sub-portafolio asignado, nunca la cuenta principal de retiro.

**Edge Cases**
*   **Data Gaps (Fines de semana/Feriados):** El script del Sandbox debe manejar `NaNs` y saltos temporales usando `pandas.fillna()` o interpolación antes de calcular medias móviles, para evitar que el script crashee.
*   **OOM en Sandbox:** Limitar la extracción de DuckDB en el Sandbox a un máximo de 5,000 velas (aprox. 1 año en timeframe diario) usando `LIMIT` en la query inyectada, protegiendo la RAM del contenedor.
*   **Flash Crashes (Circuit Breaker):** Si la volatilidad intradiaria supera el 10%, el agente aborta la generación de señales y emite una alerta de "Mercado Anómalo" a Telegram, pasando a estado *Standby*.