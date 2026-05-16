## 📈 Quant-Trader Worker

Quant-Trader es un ejecutor cuantitativo táctico en Zero-Trust: datos de mercado, señales, ejecución con HITL y, cuando el usuario o el contexto lo requieren, **lectura macro/sentimiento breve** (web/Reddit/FMP) anclada al playbook y a los tickers de sesión — sin delegar ese juicio narrativo obligatoriamente a otros workers.

---

## 🎯 Objetivo Operativo
El worker actúa como el puente entre los datos crudos del mercado y la ejecución en el broker (IBKR), asegurando que ninguna operación se proponga sin datos actualizados y ninguna orden se ejecute sin aprobación humana explícita (HITL).

---

## 🛠️ Herramientas y Capacidades

El Quant-Trader tiene acceso a un stack de herramientas especializadas:
1. *Datos de Mercado y Dividendos*
    fetch_ib_gateway_ohlcv: Obtiene velas (OHLCV) directamente desde el VPS del Gateway de IBKR. Es la fuente primaria para análisis técnico.
    fetch_market_data: Ingesta alternativa de OHLCV para marcos compatibles (persistiendo en `quant_core.ohlcv_data`).

    get_fmp_stock_dividends: Consulta el historial y próximos pagos de dividendos de un ticker vía Financial Modeling Prep.
    get_fmp_dividends_calendar: Calendario global de dividendos (ventana máx. 90 días).
    get_fmp_earnings_calendar: Calendario de reportes de earnings entre fechas (misma ventana máx. 90 días).
    get_fmp_earnings_transcript: Transcripción de earnings por ticker/año/Q; combinado con snippets/earnings_transcript_sentiment_sandbox.py para resumen compacto en sandbox sin quemar contexto LLM masivo en chat.

    tavily_search: Solo para contexto informativo (noticias/eventos), nunca para fabricar precios.

2. *Gestión de Portafolio (IBKR)*
    get_ibkr_portfolio: Snapshot en tiempo real de posiciones, valor de la cuenta y PnL.
    evaluate_cfd_state: Evalúa fase/umbral por ticker para decidir si hay contexto accionable de señal.


3. *Ejecución y Backtesting*
    execute_sandbox_script: Ejecuta scripts de Python en un entorno seguro (Strix Sandbox) para realizar backtesting de estrategias.
    propose_trade_signal: Registra una señal en el ledger para revisión humana. Aplica automáticamente el RiskGuard (ajuste de pesos según límites de riesgo).
    run_quant_signal_cycle: Tool compuesta que propone señal y, si aplica, encadena ejecución usando el `signal_id` real del ledger.
    execute_approved_signal: Envía la orden final al broker, solo si la señal tiene el flag human_approved.

4. *Comandos Fly de Operación Determinista*
    /quant_cycle: Orquesta en un solo comando `fetch -> portfolio -> evaluate -> signal`, con salida estructurada por etapas.
    /execute-signal uuid: Aprobación HITL para ejecutar una señal pendiente.
    /cancel_signal uuid: Cancelación de una señal pendiente en ledger.

---

## 🛡️ Reglas (Modo Zero-Trust)

- Para garantizar la seguridad y la integridad del capital, el worker sigue estas reglas inquebrantables:
- Evidencia Única: No se permite invocar propose_trade_signal si no se ha ejecutado exitosamente fetch_market_data o fetch_ib_gateway_ohlcv para el ticker en el turno actual.
- Ceguera Sensorial: Si la ingesta de velas falla, el agente debe reportar "Ceguera Sensorial" y detenerse. No puede inventar datos ni usar búsquedas web como sustituto de precios OHLCV.
- Aislamiento de Código: Prohibido ejecutar código en el host. Todo análisis algorítmico debe ir al Sandbox.
- HITL Obligatorio: Todas las señales requieren aprobación vía Telegram (/execute-signal <uuid>).
- Paper-Only: Por seguridad, el sistema valida que IBKR_ACCOUNT_MODE sea paper a menos que se configure explícitamente lo contrario.

---


## Estructura de Datos (DuckDB)

- El worker gestiona su estado en el esquema quant_core:
- Tabla	Descripción:

- trading_sessions: Estado de la sesión actual (ACTIVE/PAUSED), modo y tickers bajo vigilancia.
- ohlcv_data	Almacén temporal de velas para análisis (ticker, timestamp, O, H, L, C, V).
- trade_signals	Registro de señales generadas, sus precios objetivo, stop-loss y estado de aprobación.
- portfolio_positions	Copia local del estado del broker para consultas rápidas.

--- 

## Flujo de Trabajo Típico

- Activación: El usuario inicia una sesión vía Telegram:
/trading-session --mode paper --tickers NVDA,AAPL.

- Monitoreo: El reactor (o el usuario) solicita datos:
"Trae las últimas 20 velas de 1h para NVDA".

- Propuesta: Tras verificar los datos, el agente propone una señal:
"Señal generada: BUY NVDA ... signal_id=abc-123. Para aprobar: /execute-signal abc-123"

- Ejecución: Una vez aprobada, el agente ejecuta la orden en IBKR y actualiza el portfolio local.

--- 

## ⚙️ Configuración (Variables de Entorno)
- Variable	Descripción
- FMP_API_KEY	Clave para FMP: dividendos (`get_fmp_*_dividends*`), calendario de earnings y transcripts (`get_fmp_earnings_calendar`, `get_fmp_earnings_transcript`).
- IBKR_GATEWAY_OHLCV_URL	URL del endpoint de velas en el VPS.
- IBKR_ACCOUNT_MODE	paper o live.
- TAVILY_API_KEY	Para búsqueda de noticias de mercado.

--- 

## 📂 Organización de Archivos
- manifest.yaml: Define las skills habilitadas y la configuración de riesgo.
- system_prompt.md: Contiene las instrucciones lógicas y restricciones de comportamiento.
- schema.sql: DDL para inicializar las tablas en DuckDB.
- fmp_bridge.py: Implementación técnica de la integración con Financial Modeling Prep.
- factory.py: Ensamblador del grafo de LangGraph que orquestra los nodos de decisión.

---
## DIAGRAMA UML

---

```mermaid
---
config:
  layout: elk
---
classDiagram
  namespace Finance_Worker_DB {
    class Cuenta {
      +PK id: int
      +String name
      +float balance
      +String currency
    }

    class TradingMandate {
      +PK mandate_id: UUID
      +String asset_class
      +String direction
      +Decimal max_weight_pct
      +String status
    }

    class FinanceSignal {
      +PK signal_id: UUID
      +FK mandate_id
      +Boolean human_approved
      +String rationale
    }
  }

  namespace Quant_Core_DB {
    class TradingSession {
      +PK id: String
      +String mode
      +Double anchor_equity
      +Double peak_equity
    }

    class QuantSignal {
      +PK signal_id: UUID
      +Double confidence_score
      +Double target_price
      +Double stop_loss
      +String status
    }

    class PortfolioPosition {
      +PK ticker: String
      +Double qty
      +Double avg_entry_price
      +Double unrealized_pnl
    }

    class SessionTick {
      +PK id: UUID
      +String session_uid
      +JSON cfd_summary
    }
  }

  namespace External_Integrations {
    class IBKR_API {
      <<Interface>>
      +get_ibkr_portfolio()
      +fetch_ib_gateway_ohlcv()
    }

    class FMP_API {
      <<Interface>>
      +get_fmp_stock_dividends()
      +get_fmp_calendar()
    }

    class Research_Intelligence {
      <<Interface>>
      +tavily_search()
      +reddit_mcp_read()
    }
  }

  class QuantTraderWorker

  QuantTraderWorker ..> IBKR_API : "Uses for Execution"
  QuantTraderWorker ..> FMP_API : "Enriches with Data"
  QuantTraderWorker ..> Research_Intelligence : "Calculates Sentiment"
  QuantTraderWorker --> Cuenta : "Monitors Balance"
  QuantTraderWorker --> TradingMandate : "Follows Strategy"
  TradingMandate "1" -- "*" FinanceSignal : "Generates"
  TradingSession "1" -- "*" SessionTick : "Logs Activity"
  TradingSession "1" -- "*" QuantSignal : "Emits"
  QuantSignal ..> FinanceSignal : "Refines (Technical)"
  QuantSignal --> PortfolioPosition : "Affects"
  