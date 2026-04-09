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
  stop_loss DOUBLE
);

CREATE TABLE IF NOT EXISTS quant_core.portfolio_positions (
  ticker VARCHAR PRIMARY KEY,
  qty DOUBLE,
  avg_entry_price DOUBLE,
  current_price DOUBLE,
  unrealized_pnl DOUBLE,
  updated_at TIMESTAMP
);
