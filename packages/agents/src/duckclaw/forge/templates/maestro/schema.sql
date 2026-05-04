-- MAESTRO Silver — prefijo maestro_

CREATE TABLE IF NOT EXISTS maestro_curriculum (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic           VARCHAR NOT NULL,
    difficulty      INTEGER,
    prerequisites   JSON,
    resource_links  JSON,
    status          VARCHAR DEFAULT 'ACTIVE',
    updated_at      TIMESTAMPTZ DEFAULT now(),
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS maestro_study_sessions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic           VARCHAR NOT NULL,
    started_at      TIMESTAMPTZ DEFAULT now(),
    ended_at        TIMESTAMPTZ,
    streak_day      INTEGER DEFAULT 1,
    notes           TEXT,
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS maestro_milestones (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            VARCHAR NOT NULL,
    achieved_at     TIMESTAMPTZ DEFAULT now(),
    evidence_ref    VARCHAR,
    bronze_event_id UUID
);

CREATE TABLE IF NOT EXISTS maestro_quizzes (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      UUID REFERENCES maestro_study_sessions(id),
    question        TEXT NOT NULL,
    expected_answer_hint TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    bronze_event_id UUID
);
