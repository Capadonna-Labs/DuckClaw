-- analytics_core — datos analíticos aislados (spec BI Analyst)
CREATE TABLE IF NOT EXISTS analytics_core.sales (
  id UUID NOT NULL,
  fecha TIMESTAMP NOT NULL,
  producto VARCHAR NOT NULL,
  categoria VARCHAR NOT NULL,
  cantidad INTEGER NOT NULL,
  precio_unit DOUBLE NOT NULL,
  total DOUBLE NOT NULL,
  vendedor VARCHAR NOT NULL,
  region VARCHAR NOT NULL,
  canal VARCHAR NOT NULL,
  PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS analytics_core.system_metrics (
  id UUID NOT NULL,
  "timestamp" TIMESTAMP NOT NULL,
  worker_id VARCHAR NOT NULL,
  latency_ms DOUBLE NOT NULL,
  tokens_used INTEGER NOT NULL,
  status VARCHAR NOT NULL,
  error_type VARCHAR,
  PRIMARY KEY (id)
);
