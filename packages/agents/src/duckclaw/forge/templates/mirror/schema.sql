-- MIRROR Silver + Gold Tables

CREATE TABLE IF NOT EXISTS mirror_skills (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill           VARCHAR NOT NULL UNIQUE,
    level           INTEGER,  -- 0-10, NULL si sin evidencia
    evidence_count  INTEGER DEFAULT 0,
    last_practiced  TIMESTAMPTZ,
    last_updated    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS mirror_preferences (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category        VARCHAR NOT NULL,
    preference      VARCHAR NOT NULL,
    confidence      FLOAT DEFAULT 1.0,
    evidence_count  INTEGER DEFAULT 1,
    detected_at     TIMESTAMPTZ DEFAULT now()
);

-- Gold: perfil completo reconstruido por Janitor
CREATE TABLE IF NOT EXISTS gold_my_profile (
    generated_at        TIMESTAMPTZ DEFAULT now(),
    skills_json         JSON,
    preferences_json    JSON,
    active_domains      JSON,
    inactive_domains    JSON,
    connections_json    JSON,
    self_assessment     TEXT  -- actualizado por AXIS Core (CAP-CORE-001)
);
