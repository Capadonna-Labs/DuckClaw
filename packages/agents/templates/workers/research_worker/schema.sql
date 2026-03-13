-- Research Worker schema: almacenamiento de hallazgos
CREATE SCHEMA IF NOT EXISTS research_worker;

CREATE TABLE IF NOT EXISTS research_worker.findings (
    id INTEGER PRIMARY KEY,
    query TEXT,
    sources TEXT,
    summary TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
