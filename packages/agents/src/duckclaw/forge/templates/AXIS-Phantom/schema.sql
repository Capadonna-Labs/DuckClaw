-- PHANTOM Silver — prefijo phantom_

CREATE TABLE IF NOT EXISTS phantom_lab_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_title  VARCHAR NOT NULL,
    difficulty      INTEGER,
    started_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    notes           TEXT,
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS phantom_exercises (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES phantom_lab_sessions(id),
    technique_ref   VARCHAR,
    objective       TEXT NOT NULL,
    status          VARCHAR DEFAULT 'PENDING',
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS phantom_output_analysis (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES phantom_lab_sessions(id),
    raw_output_excerpt TEXT,
    analysis        TEXT NOT NULL,
    analyzed_at     TIMESTAMPTZ DEFAULT now(),
    bronze_event_id UUID
);
