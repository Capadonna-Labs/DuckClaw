CREATE TABLE IF NOT EXISTS cobranzas_worker.debts (
  id INTEGER PRIMARY KEY,
  customer_id VARCHAR NOT NULL,
  customer_name VARCHAR,
  principal_amount DOUBLE NOT NULL,
  current_balance DOUBLE NOT NULL,
  currency VARCHAR DEFAULT 'COP',
  due_date DATE,
  status VARCHAR DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cobranzas_worker.payments (
  id INTEGER PRIMARY KEY,
  debt_id INTEGER NOT NULL,
  customer_id VARCHAR NOT NULL,
  amount DOUBLE NOT NULL,
  currency VARCHAR DEFAULT 'COP',
  payment_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  payment_method VARCHAR,
  reference VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cobranzas_worker.collection_events (
  id INTEGER PRIMARY KEY,
  debt_id INTEGER,
  customer_id VARCHAR NOT NULL,
  event_type VARCHAR NOT NULL,
  event_notes VARCHAR,
  event_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_debts_customer_id
  ON cobranzas_worker.debts(customer_id);

CREATE INDEX IF NOT EXISTS idx_payments_debt_id
  ON cobranzas_worker.payments(debt_id);

CREATE INDEX IF NOT EXISTS idx_events_customer_id
  ON cobranzas_worker.collection_events(customer_id);
