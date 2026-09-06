-- DDL canónico en db-writer (reports_state_delta_handler). Referencia para el agente.
CREATE TABLE IF NOT EXISTS main.custom_reports (
  report_id VARCHAR(100) PRIMARY KEY,
  title VARCHAR(200) NOT NULL DEFAULT 'Reporte',
  html_content TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  created_by VARCHAR(200),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
