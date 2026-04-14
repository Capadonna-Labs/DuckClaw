-- GitClaw: esquema gitclaw (decisiones / ADR y log de PRs)
CREATE SCHEMA IF NOT EXISTS gitclaw;

CREATE TABLE IF NOT EXISTS gitclaw.decisions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  repo VARCHAR NOT NULL,
  title VARCHAR NOT NULL,
  context TEXT,
  decision TEXT NOT NULL,
  consequences TEXT,
  status VARCHAR DEFAULT 'active',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS gitclaw.pr_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  repo VARCHAR NOT NULL,
  pr_number INTEGER,
  title VARCHAR,
  status VARCHAR,
  reviewer_notes TEXT,
  merged_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
