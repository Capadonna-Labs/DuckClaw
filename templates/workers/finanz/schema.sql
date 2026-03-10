-- FinanzWorker: esquema aislado finance_worker
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

INSERT INTO finance_worker.categories (id, name) VALUES (1, 'Otros')
ON CONFLICT (id) DO NOTHING;
