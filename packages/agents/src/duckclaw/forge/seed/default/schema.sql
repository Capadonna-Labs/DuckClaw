-- Esquema mínimo para agentes creados desde plantilla default
CREATE SCHEMA IF NOT EXISTS agent_worker;

CREATE TABLE IF NOT EXISTS agent_worker.notes (
  id INTEGER PRIMARY KEY,
  title VARCHAR NOT NULL,
  body VARCHAR,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
