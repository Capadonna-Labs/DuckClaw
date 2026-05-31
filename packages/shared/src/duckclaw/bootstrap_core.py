"""
DDL idempotente del núcleo DuckClaw (perfil genérico / Spawn).

Spec: specs/features/platform/SPAWN_GENERIC_DEPLOY.md
Sin esquemas de dominio (quant_core, pqrsd_crm, finance_worker, run_schema forge).
"""

from __future__ import annotations

from typing import Any

from duckclaw.admin_console_users import ensure_admin_console_users_table, seed_admin_console_users_if_empty
from duckclaw.admin_user_agents import ensure_admin_user_agents_table
from duckclaw.admin_user_profiles import ensure_admin_user_profiles_table
from duckclaw.shared_db_grants import ensure_user_shared_db_access_table

_CORE_SEMANTIC_MEMORY_DDL = """
CREATE SCHEMA IF NOT EXISTS main;
CREATE TABLE IF NOT EXISTS main.semantic_memory (
  id VARCHAR PRIMARY KEY,
  content TEXT NOT NULL,
  source VARCHAR DEFAULT 'manual_injection',
  embedding FLOAT[384],
  embedding_status VARCHAR DEFAULT 'PENDING',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE main.semantic_memory ADD COLUMN IF NOT EXISTS topic VARCHAR;
ALTER TABLE main.semantic_memory ADD COLUMN IF NOT EXISTS insight TEXT;
ALTER TABLE main.semantic_memory ADD COLUMN IF NOT EXISTS confidence_score DOUBLE;
ALTER TABLE main.semantic_memory ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;
ALTER TABLE main.semantic_memory ADD COLUMN IF NOT EXISTS tenant_id VARCHAR;
"""


def bootstrap_core_schema(con: Any, *, seed_admin: bool = True) -> None:
    """
    Aplica tablas indispensables del hub en una conexión DuckDB RW.

    ``con`` puede ser ``duckdb.DuckDBPyConnection`` o adaptador con ``.execute()``.
    """
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS api_conversation (
            session_id VARCHAR NOT NULL,
            worker_id VARCHAR NOT NULL,
            role VARCHAR NOT NULL,
            content TEXT,
            author_type VARCHAR DEFAULT 'AI',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_config (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS main.authorized_users (
            tenant_id VARCHAR,
            user_id VARCHAR,
            username VARCHAR,
            role VARCHAR DEFAULT 'user',
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        );
        """
    )
    ensure_user_shared_db_access_table(con)
    ensure_admin_console_users_table(con)
    ensure_admin_user_profiles_table(con)
    ensure_admin_user_agents_table(con)
    if seed_admin:
        seed_admin_console_users_if_empty(con)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS task_audit_log (
            task_id VARCHAR PRIMARY KEY,
            tenant_id VARCHAR NOT NULL,
            worker_id VARCHAR,
            query_prefix VARCHAR,
            status VARCHAR NOT NULL,
            duration_ms INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            plan_title VARCHAR
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_conversation (
            chat_id BIGINT,
            role TEXT,
            content TEXT,
            received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    for stmt in _CORE_SEMANTIC_MEMORY_DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            con.execute(s)


def core_domain_schemas_present(con: Any) -> list[str]:
    """Nombres de esquemas de dominio que no deben existir en perfil spawn."""
    rows = con.execute(
        """
        SELECT schema_name FROM information_schema.schemata
        WHERE schema_name IN ('quant_core', 'pqrsd_crm', 'finance_worker')
        """
    ).fetchall()
    return [str(r[0]) for r in rows]
