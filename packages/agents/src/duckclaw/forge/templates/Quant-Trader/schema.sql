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

CREATE SCHEMA IF NOT EXISTS quant_core;

-- Sesión activa de trading (singleton por bóveda: id = 'active'). Fly: /trading_session
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
  outcome VARCHAR
);

CREATE TABLE IF NOT EXISTS quant_core.portfolio_positions (
  ticker VARCHAR PRIMARY KEY,
  qty DOUBLE,
  avg_entry_price DOUBLE,
  current_price DOUBLE,
  unrealized_pnl DOUBLE,
  updated_at TIMESTAMP
);
