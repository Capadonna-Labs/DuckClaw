"""DDL idempotente del núcleo DuckClaw (perfil genérico / Spawn)."""

from __future__ import annotations

import logging
from typing import Any

from duckclaw.admin_console_users import ensure_admin_console_users_table, seed_admin_console_users_if_empty
from duckclaw.admin_resources import ensure_admin_resource_tables
from duckclaw.admin_runtime_settings import ensure_admin_runtime_settings_table
from duckclaw.admin_user_agents import ensure_admin_user_agents_table
from duckclaw.admin_user_profiles import ensure_admin_user_profiles_table
from duckclaw.admin_worker_catalog import ensure_admin_worker_catalog_schema
from duckclaw.admin_workspace import ensure_admin_workspace_schema
from duckclaw.schema_migrations import run_pending_migrations
from duckclaw.shared_db_grants import ensure_user_shared_db_access_table

_log = logging.getLogger(__name__)


def bootstrap_core_schema(con: Any, *, seed_admin: bool = True) -> None:
    """
    Aplica tablas indispensables del hub en una conexión DuckDB RW.

    Ejecuta migraciones versionadas primero, luego tablas legacy
    (api_conversation, agent_config, etc.) no cubiertas por migraciones.

    ``con`` puede ser ``duckdb.DuckDBPyConnection`` o adaptador con ``.execute()``.
    """
    applied = run_pending_migrations(con)
    if applied:
        _log.info("bootstrap: %d migrations applied", len(applied))
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
    ensure_admin_worker_catalog_schema(con)
    ensure_admin_workspace_schema(con)
    ensure_admin_resource_tables(con)
    ensure_admin_runtime_settings_table(con)
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


def core_unexpected_schemas_present(con: Any, schema_names: tuple[str, ...]) -> list[str]:
    """Nombres de esquemas no esperados presentes en una conexión."""
    names = tuple(str(name).strip() for name in schema_names if str(name).strip())
    if not names:
        return []
    placeholders = ", ".join("?" for _ in names)
    rows = con.execute(
        f"SELECT schema_name FROM information_schema.schemata WHERE schema_name IN ({placeholders})",
        list(names),
    ).fetchall()
    return [str(r[0]) for r in rows]
