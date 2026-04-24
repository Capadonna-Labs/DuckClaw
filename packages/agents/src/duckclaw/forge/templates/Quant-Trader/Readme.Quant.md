## 📈 Quant-Trader Worker

Quant-Trader es un ejecutor cuantitativo táctico diseñado bajo una filosofía de Zero-Trust. Su misión es gestionar datos de mercado, evaluar señales de trading y ejecutar órdenes de forma segura, delegando el análisis macroeconómico a otros agentes (como Finanz) y operando exclusivamente bajo evidencia técnica verificable.

---

## 🎯 Objetivo Operativo
El worker actúa como el puente entre los datos crudos del mercado y la ejecución en el broker (IBKR), asegurando que ninguna operación se proponga sin datos actualizados y ninguna orden se ejecute sin aprobación humana explícita (HITL).

---

## 🛠️ Herramientas y Capacidades

El Quant-Trader tiene acceso a un stack de herramientas especializadas:
1. *Datos de Mercado y Dividendos*
 fetch_ib_gateway_ohlcv: Obtiene velas (OHLCV) directamente desde el VPS del Gateway de IBKR. Es la fuente primaria para análisis técnico.

 get_fmp_stock_dividends: Consulta el historial y próximos pagos de dividendos de un ticker vía Financial Modeling Prep.
 get_fmp_dividends_calendar: Calendario global de dividendos (ventana máx. 90 días).
 
 tavily_search: Solo para contexto informativo (noticias/eventos), nunca para fabricar precios.

2. *Gestión de Portafolio (IBKR)*
 get_ibkr_portfolio: Snapshot en tiempo real de posiciones, valor de la cuenta y PnL.


3. *Ejecución y Backtesting*
 execute_sandbox_script: Ejecuta scripts de Python en un entorno seguro (Strix Sandbox) para realizar backtesting de estrategias.
 propose_trade_signal: Registra una señal en el ledger para revisión humana. Aplica automáticamente el RiskGuard (ajuste de pesos según límites de riesgo).
 execute_approved_signal: Envía la orden final al broker, solo si la señal tiene el flag human_approved.

---

## 🛡️ Reglas (Modo Zero-Trust)

- Para garantizar la seguridad y la integridad del capital, el worker sigue estas reglas inquebrantables:
- Evidencia Única: No se permite invocar propose_trade_signal si no se ha ejecutado exitosamente fetch_market_data o fetch_ib_gateway_ohlcv para el ticker en el turno actual.
- Ceguera Sensorial: Si la ingesta de velas falla, el agente debe reportar "Ceguera Sensorial" y detenerse. No puede inventar datos ni usar búsquedas web como sustituto de precios OHLCV.
- Aislamiento de Código: Prohibido ejecutar código en el host. Todo análisis algorítmico debe ir al Sandbox.
- HITL Obligatorio: Todas las señales requieren aprobación vía Telegram (/execute_signal <uuid>).
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
/trading_session --mode paper --tickers NVDA,AAPL.

- Monitoreo: El reactor (o el usuario) solicita datos:
"Trae las últimas 20 velas de 1h para NVDA".

- Propuesta: Tras verificar los datos, el agente propone una señal:
"Señal generada: BUY NVDA ... signal_id=abc-123. Para aprobar: /execute_signal abc-123"

- Ejecución: Una vez aprobada, el agente ejecuta la orden en IBKR y actualiza el portfolio local.

--- 

## ⚙️ Configuración (Variables de Entorno)
- Variable	Descripción
- FMP_API_KEY	Clave para datos de dividendos.
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

classDiagram
    %% Capa de Aplicación (El Worker)
    class QuantTraderWorker {
        <<Service>>
        +String worker_id: quant_trader
        +String risk_profile: conservative
        +Boolean read_only: true
        +Double temperature: 0.1
        +propose_trade_signal()
        +execute_approved_signal()
        +fetch_market_data()
        +execute_sandbox_script()
    }

    %% Capa de Persistencia: Esquema Finance Worker
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

    %% Capa de Persistencia: Esquema Quant Core
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

    %% Capa de Integración (Skills / APIs Externas)
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

    %% Relaciones de Dependencia y Flujo
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