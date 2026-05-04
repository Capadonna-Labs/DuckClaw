-- SENTINEL Silver — prefijo sentinel_

CREATE TABLE IF NOT EXISTS sentinel_mitre_queries (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tactic_id       VARCHAR,
    technique_id    VARCHAR NOT NULL,
    query_text      TEXT,
    result_summary  TEXT,
    executed_at     TIMESTAMPTZ DEFAULT now(),
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS sentinel_cve_analyses (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cve_id          VARCHAR NOT NULL,
    cvss_score      FLOAT,
    analysis        TEXT NOT NULL,
    poc_summary     TEXT,
    mitigation      TEXT,
    analyzed_at     TIMESTAMPTZ DEFAULT now(),
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS sentinel_attack_scenarios (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title           VARCHAR NOT NULL,
    narrative       TEXT NOT NULL,
    mitre_refs      JSON,
    difficulty      INTEGER,
    created_at      TIMESTAMPTZ DEFAULT now(),
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS sentinel_pentest_reports (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_name VARCHAR NOT NULL,
    scope           TEXT,
    findings_json   JSON,
    status          VARCHAR DEFAULT 'DRAFT',
    created_at      TIMESTAMPTZ DEFAULT now(),
    bronze_event_id UUID
);
