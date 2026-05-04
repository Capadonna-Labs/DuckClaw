-- CODER Silver Tables
-- Prefijo obligatorio: coder_

CREATE TABLE IF NOT EXISTS coder_repos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR NOT NULL,
    language        VARCHAR NOT NULL,
    forge_project_id UUID,             -- referencia a FORGE si aplica
    description     TEXT,
    local_path      VARCHAR,
    remote_url      VARCHAR,
    last_indexed    TIMESTAMPTZ,
    status          VARCHAR DEFAULT 'ACTIVE',
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS coder_decisions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id         UUID REFERENCES coder_repos(id),
    file_path       VARCHAR,
    decision        TEXT NOT NULL,
    reason          TEXT NOT NULL,
    alternatives    JSON,
    decided_at      TIMESTAMPTZ DEFAULT now(),
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS coder_patterns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pattern_name    VARCHAR NOT NULL,
    language        VARCHAR,
    description     TEXT,
    frequency       INTEGER DEFAULT 1,
    example         TEXT,
    first_seen      TIMESTAMPTZ DEFAULT now(),
    last_seen       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS coder_errors (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    repo_id         UUID REFERENCES coder_repos(id),
    error_type      VARCHAR NOT NULL,
    error_message   TEXT,
    solution        TEXT,
    occurred_at     TIMESTAMPTZ DEFAULT now(),
    solved_at       TIMESTAMPTZ,
    bronze_event_id UUID
);
