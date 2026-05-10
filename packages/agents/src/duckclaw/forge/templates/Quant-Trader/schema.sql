-- Quant Trader: bóveda dedicada (specs/features/Quant Trader.md, Quantitative Trading Worker.md)
-- run_schema ya hace CREATE SCHEMA IF NOT EXISTS finance_worker desde manifest.schema_name

CREATE TABLE IF NOT EXISTS finance_worker.cuentas (
  id INTEGER PRIMARY KEY,
  name VARCHAR NOT NULL UNIQUE,
  balance REAL NOT NULL DEFAULT 0,
  currency VARCHAR DEFAULT 'COP',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_worker.trading_mandates (
  mandate_id UUID PRIMARY KEY,
  source_worker VARCHAR,
  asset_class VARCHAR,
  direction VARCHAR,
  max_weight_pct DECIMAL(5,2),
  status VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_worker.trade_signals (
  signal_id UUID PRIMARY KEY,
  mandate_id UUID REFERENCES finance_worker.trading_mandates(mandate_id),
  ticker VARCHAR,
  signal_type VARCHAR,
  proposed_weight DECIMAL(5,2),
  sandbox_backtest_cid VARCHAR,
  human_approved BOOLEAN DEFAULT FALSE,
  status VARCHAR,
  rationale VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE SCHEMA IF NOT EXISTS main;

CREATE TABLE IF NOT EXISTS main.semantic_memory (
  id VARCHAR PRIMARY KEY,
  content TEXT NOT NULL,
  source VARCHAR DEFAULT 'manual_injection',
  embedding FLOAT[384],
  embedding_status VARCHAR DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE SCHEMA IF NOT EXISTS quant_core;

-- Sesión activa de trading (singleton por bóveda: id = 'active'). Fly: /trading_session
-- session_goal JSON: objective maximize_pnl|rebalance_hrp, max_drawdown_pct, position_size_pct, signal_threshold, tickers, mode
CREATE TABLE IF NOT EXISTS quant_core.trading_sessions (
  id VARCHAR PRIMARY KEY,
  mode VARCHAR NOT NULL,
  tickers VARCHAR NOT NULL DEFAULT '',
  session_uid VARCHAR,
  session_goal JSON,
  status VARCHAR NOT NULL DEFAULT 'ACTIVE',
  anchor_equity DOUBLE,
  peak_equity DOUBLE,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quant_core.trading_risk_constraints (
  id VARCHAR PRIMARY KEY,
  max_drawdown_pct DOUBLE,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quant_core.ohlcv_data (
  ticker VARCHAR,
  timestamp TIMESTAMP,
  open DOUBLE,
  high DOUBLE,
  low DOUBLE,
  close DOUBLE,
  volume DOUBLE,
  PRIMARY KEY (ticker, timestamp)
);

CREATE TABLE IF NOT EXISTS quant_core.trade_signals (
  signal_id UUID PRIMARY KEY,
  ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  ticker VARCHAR,
  strategy_name VARCHAR,
  action VARCHAR,
  confidence_score DOUBLE,
  target_price DOUBLE,
  stop_loss DOUBLE,
  order_qty DOUBLE,
  session_uid VARCHAR,
  rationale TEXT,
  status VARCHAR DEFAULT 'PENDING_HITL',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quant_core.session_ticks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_uid VARCHAR NOT NULL,
  tick_number INTEGER NOT NULL,
  fired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  tickers_processed VARCHAR[],
  signals_proposed INTEGER DEFAULT 0,
  cfd_summary JSON,
  outcome VARCHAR,
  moc_executed BOOLEAN DEFAULT FALSE,
  moc_notional DECIMAL(15, 2),
  moc_n_orders INTEGER
);

-- Core-Satellite: pesos HRP semanales + MOC CFD (specs/features/Core-Satellite HRP Weekly + MOC CFD.md)
CREATE TABLE IF NOT EXISTS quant_core.hrp_mandates (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticker VARCHAR(20) NOT NULL,
  hrp_weight DOUBLE NOT NULL,
  hrp_weight_capped DOUBLE NOT NULL,
  lookback_days INTEGER NOT NULL,
  n_observations INTEGER NOT NULL,
  computed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  valid_until TIMESTAMP NOT NULL,
  shrinkage_method VARCHAR(50) DEFAULT 'ledoit_wolf'
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_hrp_mandates_ticker_day
  ON quant_core.hrp_mandates (ticker, date_trunc('day', computed_at));

-- Acumulador intradía MOC (hints hasta calc PM2) — specs/features/Core-Satellite HRP Weekly + MOC CFD.md
CREATE TABLE IF NOT EXISTS quant_core.intraday_moc_accum (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_uid VARCHAR NOT NULL,
  ticker VARCHAR(20) NOT NULL,
  trading_date DATE NOT NULL,
  payload JSON NOT NULL DEFAULT '{}',
  finalized_at TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(session_uid, ticker, trading_date)
);

CREATE TABLE IF NOT EXISTS quant_core.portfolio_positions (
  ticker VARCHAR PRIMARY KEY,
  qty DOUBLE,
  avg_entry_price DOUBLE,
  current_price DOUBLE,
  unrealized_pnl DOUBLE,
  updated_at TIMESTAMP
);

-- CFD snapshots (evaluate_cfd_state / record_fluid_state); alineado con finanz/schema.sql
CREATE TABLE IF NOT EXISTS quant_core.fluid_state (
  ticker VARCHAR NOT NULL,
  timestamp TIMESTAMP NOT NULL,
  hex_signature VARCHAR NOT NULL,
  mass DOUBLE,
  density DOUBLE,
  temperature DOUBLE,
  pressure DOUBLE,
  viscosity DOUBLE,
  surface_tension DOUBLE,
  delta DOUBLE,
  gamma DOUBLE,
  vega DOUBLE,
  theta DOUBLE,
  phase VARCHAR NOT NULL,
  PRIMARY KEY (ticker, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_fluid_state_ticker ON quant_core.fluid_state (ticker);

-- MOC macro grafo PGQ + override manual — specs/features/MOC Macro PGQ VSS.md
CREATE TABLE IF NOT EXISTS quant_core.macro_nodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_type VARCHAR(50) NOT NULL,
    name VARCHAR(100) NOT NULL UNIQUE,
    properties JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS quant_core.macro_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    src_node_id UUID REFERENCES quant_core.macro_nodes(id),
    dst_node_id UUID REFERENCES quant_core.macro_nodes(id),
    edge_type VARCHAR(60) NOT NULL,
    weight DECIMAL(8,4),
    valid_from TIMESTAMP,
    valid_until TIMESTAMP,
    evidence TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_macro_edges_src ON quant_core.macro_edges(src_node_id);
CREATE INDEX IF NOT EXISTS idx_macro_edges_dst ON quant_core.macro_edges(dst_node_id);
CREATE INDEX IF NOT EXISTS idx_macro_edges_type ON quant_core.macro_edges(edge_type);

CREATE TABLE IF NOT EXISTS quant_core.macro_manual_state (
    id VARCHAR PRIMARY KEY,
    regime_override VARCHAR,
    confidence DOUBLE,
    evidence TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
