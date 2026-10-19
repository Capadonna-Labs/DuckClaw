-- Portafolio manual: posiciones registradas por el usuario y precios de cierre observados.
CREATE SCHEMA IF NOT EXISTS agent_worker;

CREATE TABLE IF NOT EXISTS agent_worker.holdings (
  id VARCHAR PRIMARY KEY,            -- uuid()
  broker VARCHAR NOT NULL,           -- nombre del bróker o app (texto libre)
  symbol VARCHAR NOT NULL,           -- como lo muestra el bróker (p. ej. ECOPETROL, AAPLCO, VOO)
  price_symbol VARCHAR,              -- símbolo en yfinance (ECOPETROL.CL, AAPL, VOO); NULL = precio manual
  market VARCHAR,                    -- BVC, NYSE, NASDAQ, fondo, etc.
  quantity DOUBLE NOT NULL,
  avg_cost DOUBLE,                   -- costo promedio por unidad, en currency
  currency VARCHAR NOT NULL DEFAULT 'COP',  -- moneda en la que el usuario tiene la posición
  price_currency VARCHAR,            -- moneda del precio de price_symbol si difiere (p. ej. USD)
  notes VARCHAR,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_worker.price_marks (
  price_symbol VARCHAR NOT NULL,
  mark_date DATE NOT NULL,
  close DOUBLE NOT NULL,
  currency VARCHAR,
  source VARCHAR NOT NULL,           -- yfinance | manual
  recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (price_symbol, mark_date)
);
