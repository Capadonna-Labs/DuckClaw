-- FinanzWorker: esquema aislado finance_worker
-- Transacciones y categorías
CREATE TABLE IF NOT EXISTS finance_worker.transactions (
  id INTEGER PRIMARY KEY,
  amount REAL NOT NULL,
  description VARCHAR,
  category_id INTEGER,
  tx_date DATE DEFAULT CURRENT_DATE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_worker.categories (
  id INTEGER PRIMARY KEY,
  name VARCHAR NOT NULL UNIQUE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cuentas (Bancolombia, Nequi, Efectivo, etc.)
CREATE TABLE IF NOT EXISTS finance_worker.cuentas (
  id INTEGER PRIMARY KEY,
  name VARCHAR NOT NULL UNIQUE,
  balance REAL NOT NULL DEFAULT 0,
  currency VARCHAR DEFAULT 'COP',
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_worker.deudas (
  id INTEGER PRIMARY KEY,
  description VARCHAR,
  amount REAL NOT NULL,
  creditor VARCHAR,
  due_date DATE,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS finance_worker.presupuestos (
  id INTEGER PRIMARY KEY,
  category_id INTEGER NOT NULL,
  amount REAL NOT NULL,
  year INTEGER NOT NULL,
  month INTEGER NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_presupuestos_cat_ym ON finance_worker.presupuestos (category_id, year, month);

-- OSINT JobHunter + seguimiento de postulaciones (spec OSINT JobHunter, A2A JOB_OPPORTUNITY_TRACKING)
CREATE TABLE IF NOT EXISTS finance_worker.job_opportunities (
  title VARCHAR,
  company VARCHAR,
  location VARCHAR,
  salary_range VARCHAR,
  requirements VARCHAR,
  apply_url VARCHAR,
  source_url VARCHAR,
  scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  status VARCHAR,
  applied_at TIMESTAMP,
  notes VARCHAR
);
CREATE INDEX IF NOT EXISTS idx_job_opportunities_apply_url ON finance_worker.job_opportunities (apply_url);

-- Migración desde tablas creadas antes de status/applied_at/notes (CREATE IF NOT EXISTS no altera columnas)
ALTER TABLE finance_worker.job_opportunities ADD COLUMN IF NOT EXISTS status VARCHAR;
ALTER TABLE finance_worker.job_opportunities ADD COLUMN IF NOT EXISTS applied_at TIMESTAMP;
ALTER TABLE finance_worker.job_opportunities ADD COLUMN IF NOT EXISTS notes VARCHAR;

-- Idempotencia por URL (si falla: hay apply_url duplicados; deduplicar y volver a aplicar schema)
CREATE UNIQUE INDEX IF NOT EXISTS idx_job_opportunities_apply_url_unique ON finance_worker.job_opportunities (apply_url);

INSERT INTO finance_worker.categories (id, name) VALUES (1, 'Otros')
ON CONFLICT (id) DO NOTHING;

-- Quantitative trading (spec: Quantitative Trading Worker) — misma bóveda Finanz
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

-- Cyber-Fluid Dynamics (CFD) — spec: Cyber-Fluid Dynamics CFD (Finanz).md
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
    phase VARCHAR NOT NULL,
    PRIMARY KEY (ticker, timestamp)
);
CREATE INDEX IF NOT EXISTS idx_fluid_state_ticker ON quant_core.fluid_state (ticker);
