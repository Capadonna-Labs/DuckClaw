CREATE TABLE IF NOT EXISTS radar_cves (
    cve_id          VARCHAR PRIMARY KEY,
    cvss_score      FLOAT,
    description     TEXT,
    published_at    TIMESTAMPTZ,
    aplica_mi_stack BOOLEAN DEFAULT FALSE,
    patched         BOOLEAN DEFAULT FALSE,
    ingested_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS radar_news (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    url             VARCHAR UNIQUE,
    title           VARCHAR,
    summary         TEXT,
    tags            JSON,
    relevance_score FLOAT,
    published_at    TIMESTAMPTZ,
    ingested_at     TIMESTAMPTZ DEFAULT now()
);
