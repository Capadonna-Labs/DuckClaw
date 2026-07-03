"""Versioned schema migrations for DuckClaw DuckDB hub.

Each migration carries explicit DDL strings. Checksum is computed over
the concatenated DDL so any schema change is detected as drift.

Usage::

    from duckclaw.schema_migrations import run_pending_migrations

    run_pending_migrations(db)  # on gateway startup
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable

_log = logging.getLogger(__name__)

MigrationHook = Callable[[Any], None]

# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

_MIGRATIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS main.schema_migrations (
    version INTEGER PRIMARY KEY,
    name VARCHAR NOT NULL,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    checksum VARCHAR NOT NULL
)
"""


def _checksum(ddl_statements: list[str]) -> str:
    raw = "\n".join(ddl_statements)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def ensure_migrations_table(db: Any) -> None:
    db.execute(_MIGRATIONS_TABLE_DDL)


def applied_versions(db: Any, *, create_table: bool = True) -> set[int]:
    if create_table:
        ensure_migrations_table(db)
    try:
        rows = db.execute(
            "SELECT version, checksum FROM main.schema_migrations ORDER BY version"
        ).fetchall()
        return {int(r[0]) for r in rows}
    except Exception:
        return set()


def applied_with_checksums(db: Any, *, create_table: bool = True) -> dict[int, str]:
    if create_table:
        ensure_migrations_table(db)
    try:
        rows = db.execute(
            "SELECT version, checksum FROM main.schema_migrations ORDER BY version"
        ).fetchall()
        return {int(r[0]): str(r[1]) for r in rows}
    except Exception:
        return {}


def run_pending_migrations(db: Any) -> list[str]:
    """Apply all pending migrations. Returns list of migration names applied.

    Each migration runs in its own transaction (BEGIN/COMMIT). If migration
    DDL succeeds but the version record insertion fails, everything rolls back.
    Already-applied versions are silently skipped.

    Drift detection: if an already-applied version's DDL checksum differs from
    the current definition, a warning is logged but startup is not blocked.
    """
    ensure_migrations_table(db)
    current_checksums = applied_with_checksums(db)
    applied_names: list[str] = []

    for version, name, ddl in sorted(_ALL_MIGRATIONS):
        chk = _checksum(ddl)

        # Drift detection — log warning, don't block
        if version in current_checksums:
            if current_checksums[version] != chk:
                _log.warning(
                    "migration %s drift: expected checksum %s, got %s. "
                    "The DDL definition changed after this version was applied.",
                    name,
                    current_checksums[version],
                    chk,
                )
            continue

        # Apply migration in a transaction
        try:
            db.execute("BEGIN TRANSACTION")
            for stmt in ddl:
                sql = stmt.strip()
                if sql:
                    db.execute(sql)
            hook = _MIGRATION_HOOKS.get(version)
            if hook is not None:
                hook(db)
            db.execute(
                "INSERT INTO main.schema_migrations (version, name, checksum) "
                "VALUES (?, ?, ?)",
                [version, name, chk],
            )
            db.execute("COMMIT")
            applied_names.append(f"{version:03d}_{name}")
            _log.info("migration applied: %s", applied_names[-1])
        except Exception as exc:
            try:
                db.execute("ROLLBACK")
            except Exception:
                pass
            _log.error("migration %s failed, rolled back: %s", name, exc)
            raise

    return applied_names


def verify_migration_integrity(db: Any) -> list[str]:
    """Return list of drift descriptions. Empty list = clean.

    Called from tests to assert no drift. Does not alter the database.
    """
    current = applied_with_checksums(db)
    drifts: list[str] = []
    for version, name, ddl in sorted(_ALL_MIGRATIONS):
        if version not in current:
            continue
        expected = _checksum(ddl)
        if current[version] != expected:
            drifts.append(
                f"version={version} name={name} "
                f"registered={current[version]} "
                f"current_definition={expected}"
            )
    return drifts


def verify_schema_integrity(db_path: str) -> tuple[bool, str]:
    """Verify gateway DuckDB exists and all versioned migrations are applied.

    Returns ``(ok, message)``. When ``DUCKCLAW_SCHEMA_STRICT=1``, checksum drift
    also fails verification.
    """
    import os
    from pathlib import Path

    path = Path((db_path or "").strip()).expanduser()
    if not path.is_file():
        return False, f"Gateway database not found at {path}. Run: duckclaw-migrate"

    import duckdb

    con = duckdb.connect(str(path), read_only=True)
    try:
        applied = applied_versions(con, create_table=False)
        expected_versions = {version for version, _, _ in _ALL_MIGRATIONS}
        missing = sorted(expected_versions - applied)
        if missing:
            return (
                False,
                f"Pending schema migrations: {missing}. Run: duckclaw-migrate",
            )

        strict = (os.environ.get("DUCKCLAW_SCHEMA_STRICT") or "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if strict:
            current = applied_with_checksums(con, create_table=False)
            drifts: list[str] = []
            for version, name, ddl in sorted(_ALL_MIGRATIONS):
                if version not in current:
                    continue
                expected = _checksum(ddl)
                if current[version] != expected:
                    drifts.append(
                        f"version={version} name={name} "
                        f"registered={current[version]} "
                        f"current_definition={expected}"
                    )
            if drifts:
                return False, f"Schema drift detected: {drifts[0]}"
        return True, "ok"
    finally:
        con.close()


def migrate_gateway_database(db_path: str, *, seed_admin: bool = True) -> list[int]:
    """Apply pending migrations and core bootstrap DDL to the gateway DuckDB."""
    from pathlib import Path

    import duckdb

    from duckclaw.bootstrap_core import bootstrap_core_schema

    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)

    class _Adapter:
        __slots__ = ("_con",)

        def __init__(self, con: Any) -> None:
            self._con = con

        def execute(self, sql: str, params=None):
            if params is not None:
                return self._con.execute(sql, params)
            return self._con.execute(sql)

    con = duckdb.connect(str(path), read_only=False)
    try:
        adapter = _Adapter(con)
        before = applied_versions(con)
        bootstrap_core_schema(adapter, seed_admin=seed_admin)
        after = applied_versions(con)
        return sorted(after - before)
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Migration definitions
# Each entry: (version, name, [ddl_statement, ...])
# DDL is copied from current module-level DDL constants to guarantee
# that the migration produces the exact schema the rest of the code expects.
# ---------------------------------------------------------------------------

_M001_INITIAL_CORE = [
    # admin_console_users (from admin_console_users.py:_ADMIN_CONSOLE_USERS_DDL)
    """
    CREATE TABLE IF NOT EXISTS main.admin_console_users (
        email VARCHAR PRIMARY KEY,
        nombre VARCHAR NOT NULL,
        rol VARCHAR NOT NULL DEFAULT 'viewer',
        password_hash VARCHAR NOT NULL,
        initials VARCHAR,
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # auth columns (from admin_console_users.py:_AUTH_COLUMN_MIGRATIONS)
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS hash_algo TEXT DEFAULT 'pbkdf2_sha256'",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS hash_params JSON",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMP",
    # admin_user_profiles (from admin_user_profiles.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_user_profiles (
        email VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL UNIQUE,
        telegram_user_id VARCHAR,
        channels_json TEXT,
        default_worker_id VARCHAR DEFAULT 'default',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # admin_user_agents (from admin_user_agents.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_user_agents (
        tenant_id VARCHAR NOT NULL,
        owner_email VARCHAR NOT NULL,
        worker_id VARCHAR NOT NULL,
        display_name VARCHAR NOT NULL,
        source_template_id VARCHAR DEFAULT 'default',
        manifest_path VARCHAR NOT NULL,
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, worker_id)
    )
    """,
    # admin_worker_catalog (from admin_worker_catalog.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_worker_catalog (
        worker_uid VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL,
        owner_email VARCHAR NOT NULL,
        worker_id VARCHAR NOT NULL,
        display_name VARCHAR NOT NULL,
        source_kind VARCHAR DEFAULT 'runtime',
        source_template_id VARCHAR DEFAULT 'default',
        visibility VARCHAR DEFAULT 'private',
        status VARCHAR DEFAULT 'active',
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (tenant_id, worker_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_worker_catalog_owner
        ON main.admin_worker_catalog (tenant_id, owner_email, active)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_worker_catalog_visibility
        ON main.admin_worker_catalog (visibility, active)
    """,
]

_M002_WORKER_VERSIONS = [
    # admin_worker_versions (from admin_worker_catalog.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_worker_versions (
        worker_uid VARCHAR NOT NULL,
        version INTEGER NOT NULL,
        manifest_snapshot_json TEXT,
        files_snapshot_json TEXT,
        created_by VARCHAR NOT NULL,
        change_note VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (worker_uid, version)
    )
    """,
]

_M003_WORKER_CONTEXTS = [
    # admin_worker_contexts (from admin_worker_catalog.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_worker_contexts (
        context_id VARCHAR PRIMARY KEY,
        worker_uid VARCHAR NOT NULL,
        title VARCHAR NOT NULL,
        content_md TEXT NOT NULL,
        sort_order INTEGER DEFAULT 0,
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_worker_contexts_worker
        ON main.admin_worker_contexts (worker_uid, active, sort_order)
    """,
]

_M004_ASSIGNMENTS = [
    # admin_worker_assignments (from admin_worker_catalog.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_worker_assignments (
        worker_uid VARCHAR NOT NULL,
        target_email VARCHAR NOT NULL,
        target_tenant_id VARCHAR,
        permission VARCHAR NOT NULL DEFAULT 'use',
        assigned_by VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (worker_uid, target_email, permission)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_worker_assignments_target
        ON main.admin_worker_assignments (target_email, target_tenant_id)
    """,
]

_M005_SKILLS_AND_CAPS = [
    # admin_skills (from admin_worker_catalog.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_skills (
        skill_id VARCHAR PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        description TEXT,
        skill_type VARCHAR NOT NULL,
        implementation_ref VARCHAR NOT NULL,
        owner_email VARCHAR,
        tenant_id VARCHAR DEFAULT 'global',
        visibility VARCHAR DEFAULT 'private',
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # admin_worker_skills (from admin_worker_catalog.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_worker_skills (
        worker_uid VARCHAR NOT NULL,
        skill_id VARCHAR NOT NULL,
        enabled BOOLEAN DEFAULT true,
        config_json TEXT,
        sort_order INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (worker_uid, skill_id)
    )
    """,
    # admin_capabilities (from admin_worker_catalog.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_capabilities (
        capability_id VARCHAR PRIMARY KEY,
        name VARCHAR NOT NULL UNIQUE,
        kind VARCHAR NOT NULL,
        provider VARCHAR NOT NULL,
        description TEXT,
        schema_json TEXT,
        risk_level VARCHAR DEFAULT 'low',
        requires_secret BOOLEAN DEFAULT false,
        requires_network BOOLEAN DEFAULT false,
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # admin_worker_capabilities (from admin_worker_catalog.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_worker_capabilities (
        worker_uid VARCHAR NOT NULL,
        capability_id VARCHAR NOT NULL,
        permission VARCHAR NOT NULL DEFAULT 'use',
        config_json TEXT,
        policy_json TEXT,
        quota_json TEXT,
        enabled BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (worker_uid, capability_id)
    )
    """,
]

_M006_PROJECTS = [
    # admin_projects (from admin_workspace.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_projects (
        project_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL,
        owner_email VARCHAR NOT NULL,
        name VARCHAR NOT NULL,
        description TEXT,
        status VARCHAR DEFAULT 'active',
        visibility VARCHAR DEFAULT 'private',
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_projects_owner
        ON main.admin_projects (tenant_id, owner_email, status)
    """,
    # admin_project_members (from admin_workspace.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_project_members (
        project_id VARCHAR NOT NULL,
        email VARCHAR NOT NULL,
        role VARCHAR NOT NULL DEFAULT 'member',
        assigned_by VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (project_id, email)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_project_members_email
        ON main.admin_project_members (email)
    """,
    # admin_project_agents (from admin_workspace.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_project_agents (
        project_id VARCHAR NOT NULL,
        worker_uid VARCHAR NOT NULL,
        role VARCHAR NOT NULL DEFAULT 'member',
        sort_order INTEGER DEFAULT 0,
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (project_id, worker_uid)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_project_agents_worker
        ON main.admin_project_agents (worker_uid)
    """,
]

_M007_RUNTIME_SETTINGS = [
    """
    CREATE TABLE IF NOT EXISTS main.admin_runtime_settings (
        setting_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL DEFAULT 'global',
        actor_email VARCHAR NOT NULL DEFAULT '',
        domain VARCHAR NOT NULL,
        key VARCHAR NOT NULL,
        value_text TEXT,
        value_json TEXT,
        value_kind VARCHAR NOT NULL DEFAULT 'string',
        secret BOOLEAN DEFAULT false,
        source VARCHAR NOT NULL DEFAULT 'db',
        active BOOLEAN DEFAULT true,
        created_by VARCHAR,
        updated_by VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (tenant_id, actor_email, domain, key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_runtime_settings_lookup
        ON main.admin_runtime_settings (tenant_id, actor_email, domain, key, active)
    """,
]

_M008_RESOURCES = [
    # admin_resource_events (from admin_resources.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_resource_events (
        event_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL,
        actor_email VARCHAR NOT NULL,
        resource_kind VARCHAR NOT NULL,
        resource_id VARCHAR NOT NULL,
        event_type VARCHAR NOT NULL,
        payload_redacted_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_resource_events_tenant_created
        ON main.admin_resource_events (tenant_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_resource_events_resource
        ON main.admin_resource_events (resource_kind, resource_id)
    """,
    # admin_resource_tags (from admin_resources.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_resource_tags (
        resource_kind VARCHAR NOT NULL,
        resource_id VARCHAR NOT NULL,
        tag VARCHAR NOT NULL,
        created_by VARCHAR,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (resource_kind, resource_id, tag)
    )
    """,
    # admin_secret_refs (from admin_resources.py)
    """
    CREATE TABLE IF NOT EXISTS main.admin_secret_refs (
        secret_ref VARCHAR PRIMARY KEY,
        owner_email VARCHAR,
        tenant_id VARCHAR NOT NULL,
        provider VARCHAR NOT NULL,
        purpose VARCHAR NOT NULL,
        env_key VARCHAR,
        status VARCHAR DEFAULT 'active',
        rotated_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
]

_M009_SHARED_DB_GRANTS = [
    # user_shared_db_access (from shared_db_grants.py)
    """
    CREATE TABLE IF NOT EXISTS main.user_shared_db_access (
        tenant_id VARCHAR NOT NULL,
        user_id VARCHAR NOT NULL,
        resource_key VARCHAR NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, user_id, resource_key)
    )
    """,
]

_M010_WRITE_LEDGER = [
    # admin_write_ledger — idempotencia/auditoría de writes
    """
    CREATE TABLE IF NOT EXISTS main.admin_write_ledger (
        task_id VARCHAR PRIMARY KEY,
        command_type VARCHAR NOT NULL,
        command_json TEXT NOT NULL,
        status VARCHAR DEFAULT 'pending',
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        processed_at TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_write_ledger_status
        ON main.admin_write_ledger (status, created_at)
    """,
]

_M011_CONVERSATIONS = [
    # admin_conversations — chat sessions per tenant/user
    """
    CREATE TABLE IF NOT EXISTS main.admin_conversations (
        conversation_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL DEFAULT 'default',
        actor_email VARCHAR NOT NULL DEFAULT '',
        title VARCHAR DEFAULT '',
        worker_id VARCHAR DEFAULT '',
        vault_path VARCHAR DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_conversations_actor
        ON main.admin_conversations (tenant_id, actor_email, updated_at)
    """,
    # admin_conversation_messages — individual messages
    """
    CREATE TABLE IF NOT EXISTS main.admin_conversation_messages (
        message_id VARCHAR PRIMARY KEY,
        conversation_id VARCHAR NOT NULL,
        role VARCHAR NOT NULL,
        content TEXT,
        artifact_json TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conv_messages_conversation
        ON main.admin_conversation_messages (conversation_id, created_at)
    """,
    # admin_conversation_artifacts — file metadata from chat (images, etc.)
    """
    CREATE TABLE IF NOT EXISTS main.admin_conversation_artifacts (
        artifact_id VARCHAR PRIMARY KEY,
        conversation_id VARCHAR NOT NULL,
        message_id VARCHAR,
        file_type VARCHAR NOT NULL,
        file_path VARCHAR NOT NULL,
        file_size_bytes BIGINT DEFAULT 0,
        mime_type VARCHAR DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_conv_artifacts_conversation
        ON main.admin_conversation_artifacts (conversation_id, created_at)
    """,
]

_M012_KANBAN = [
    # admin_kanban_cards — planning board items
    """
    CREATE TABLE IF NOT EXISTS main.admin_kanban_cards (
        card_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL DEFAULT 'default',
        actor_email VARCHAR NOT NULL DEFAULT '',
        title VARCHAR NOT NULL,
        description TEXT DEFAULT '',
        status VARCHAR DEFAULT 'todo'
            CHECK (status IN ('todo', 'in_progress', 'done', 'cancelled')),
        priority INTEGER DEFAULT 0,
        sort_order INTEGER DEFAULT 0,
        assignee_email VARCHAR DEFAULT '',
        tags_json TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kanban_cards_actor
        ON main.admin_kanban_cards (tenant_id, actor_email, status, sort_order)
    """,
    # admin_kanban_events — card history
    """
    CREATE TABLE IF NOT EXISTS main.admin_kanban_events (
        event_id VARCHAR PRIMARY KEY,
        card_id VARCHAR NOT NULL,
        event_type VARCHAR NOT NULL,
        payload_json TEXT,
        actor_email VARCHAR NOT NULL DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_kanban_events_card
        ON main.admin_kanban_events (card_id, created_at)
    """,
]

_M013_WORKFLOWS = [
    # admin_workflows — ComfyUI workflow templates
    """
    CREATE TABLE IF NOT EXISTS main.admin_workflows (
        workflow_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL DEFAULT 'global',
        name VARCHAR NOT NULL,
        description TEXT DEFAULT '',
        category VARCHAR DEFAULT 'general',
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS idx_admin_workflows_name
        ON main.admin_workflows (tenant_id, name)
    """,
    # admin_workflow_versions — versioned workflow JSON
    """
    CREATE TABLE IF NOT EXISTS main.admin_workflow_versions (
        workflow_id VARCHAR NOT NULL,
        version INTEGER NOT NULL,
        workflow_json TEXT NOT NULL,
        metadata_json TEXT DEFAULT '{}',
        created_by VARCHAR NOT NULL DEFAULT 'system',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (workflow_id, version)
    )
    """,
    # admin_visual_assets — generated image metadata
    """
    CREATE TABLE IF NOT EXISTS main.admin_visual_assets (
        asset_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL DEFAULT 'default',
        request_json TEXT NOT NULL,
        workflow_id VARCHAR,
        asset_path VARCHAR,
        image_base64_preview TEXT,
        prompt TEXT DEFAULT '',
        status VARCHAR DEFAULT 'pending'
            CHECK (status IN ('pending', 'generating', 'completed', 'failed')),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_visual_assets_tenant
        ON main.admin_visual_assets (tenant_id, status, created_at)
    """,
]

_M014_TOOLS = [
    # admin_tool_servers — MCP server configurations
    # NOTE: env_public_json is for NON-SECRET environment metadata (tags, labels, etc.)
    # Secrets (API keys, tokens) MUST use admin_secret_refs, not this field.
    """
    CREATE TABLE IF NOT EXISTS main.admin_tool_servers (
        server_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL DEFAULT 'global',
        name VARCHAR NOT NULL,
        transport VARCHAR NOT NULL DEFAULT 'stdio'
            CHECK (transport IN ('stdio', 'http', 'docker')),
        command VARCHAR DEFAULT '',
        args_json TEXT DEFAULT '[]',
        env_public_json TEXT DEFAULT '{}'
            CHECK (
                json_valid(env_public_json)
                AND NOT regexp_matches(
                    lower(env_public_json),
                    '"[^"]*(secret|token|password|api[_-]?key|apikey)[^"]*"[[:space:]]*:'
                )
            ),
        url VARCHAR DEFAULT '',
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    # admin_tool_bindings — which workers can use which tools
    """
    CREATE TABLE IF NOT EXISTS main.admin_tool_bindings (
        binding_id VARCHAR PRIMARY KEY,
        server_id VARCHAR NOT NULL,
        worker_uid VARCHAR NOT NULL,
        tools_csv VARCHAR DEFAULT '*',
        enabled BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (server_id, worker_uid)
    )
    """,
    # admin_tool_policies — security policies for tool invocation
    """
    CREATE TABLE IF NOT EXISTS main.admin_tool_policies (
        policy_id VARCHAR PRIMARY KEY,
        worker_uid VARCHAR NOT NULL,
        tool_name VARCHAR NOT NULL,
        allow_network BOOLEAN DEFAULT false,
        allow_file_read BOOLEAN DEFAULT false,
        allow_file_write BOOLEAN DEFAULT false,
        max_execution_seconds INTEGER DEFAULT 30,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (worker_uid, tool_name)
    )
    """,
]

_M015_KNOWLEDGE = [
    """
    CREATE TABLE IF NOT EXISTS main.admin_knowledge_sources (
        source_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL DEFAULT 'default',
        actor_email VARCHAR NOT NULL DEFAULT 'system',
        project_id VARCHAR DEFAULT '',
        worker_uid VARCHAR DEFAULT '',
        source_kind VARCHAR NOT NULL DEFAULT 'folder'
            CHECK (source_kind IN ('folder', 'file', 'url', 'manual', 'api')),
        source_uri TEXT NOT NULL,
        display_name VARCHAR DEFAULT '',
        status VARCHAR NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending', 'indexing', 'ready', 'failed', 'inactive')),
        embedding_model VARCHAR DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
        embedding_dim INTEGER DEFAULT 384,
        metadata_json TEXT DEFAULT '{}'
            CHECK (json_valid(metadata_json)),
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_knowledge_sources_scope
        ON main.admin_knowledge_sources (tenant_id, project_id, worker_uid, active, status)
    """,
    """
    CREATE TABLE IF NOT EXISTS main.admin_knowledge_documents (
        document_id VARCHAR PRIMARY KEY,
        source_id VARCHAR NOT NULL,
        relative_path TEXT NOT NULL,
        title VARCHAR DEFAULT '',
        mime_type VARCHAR DEFAULT 'text/plain',
        checksum VARCHAR NOT NULL,
        byte_size BIGINT DEFAULT 0,
        metadata_json TEXT DEFAULT '{}'
            CHECK (json_valid(metadata_json)),
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (source_id, relative_path)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_knowledge_documents_source
        ON main.admin_knowledge_documents (source_id, active, checksum)
    """,
    """
    CREATE TABLE IF NOT EXISTS main.admin_knowledge_chunks (
        chunk_id VARCHAR PRIMARY KEY,
        document_id VARCHAR NOT NULL,
        source_id VARCHAR NOT NULL,
        tenant_id VARCHAR NOT NULL DEFAULT 'default',
        project_id VARCHAR DEFAULT '',
        worker_uid VARCHAR DEFAULT '',
        chunk_index INTEGER NOT NULL,
        content TEXT NOT NULL,
        content_hash VARCHAR NOT NULL,
        start_offset INTEGER DEFAULT 0,
        end_offset INTEGER DEFAULT 0,
        token_count INTEGER DEFAULT 0,
        embedding FLOAT[384],
        embedding_status VARCHAR NOT NULL DEFAULT 'PENDING'
            CHECK (embedding_status IN ('PENDING', 'READY', 'FAILED')),
        embedding_model VARCHAR DEFAULT 'sentence-transformers/all-MiniLM-L6-v2',
        metadata_json TEXT DEFAULT '{}'
            CHECK (json_valid(metadata_json)),
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (document_id, chunk_index)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_knowledge_chunks_scope
        ON main.admin_knowledge_chunks (tenant_id, project_id, worker_uid, active, embedding_status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_knowledge_chunks_source
        ON main.admin_knowledge_chunks (source_id, document_id, active)
    """,
]

_M016_PROMPT_POLICIES = [
    """
    CREATE TABLE IF NOT EXISTS main.prompt_policy_registry (
        policy_id VARCHAR PRIMARY KEY,
        policy_type VARCHAR NOT NULL
            CHECK (policy_type IN ('directive', 'capability', 'system_prompt', 'manager_task', 'tool_directive')),
        policy_name VARCHAR NOT NULL,
        version INTEGER NOT NULL DEFAULT 1,
        status VARCHAR NOT NULL DEFAULT 'active'
            CHECK (status IN ('draft', 'active', 'inactive', 'archived')),
        content TEXT NOT NULL,
        checksum VARCHAR NOT NULL,
        metadata_json TEXT DEFAULT '{}'
            CHECK (json_valid(metadata_json)),
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (policy_type, policy_name, version)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_prompt_policy_registry_lookup
        ON main.prompt_policy_registry (policy_type, policy_name, active, status, version)
    """,
    """
    CREATE TABLE IF NOT EXISTS main.worker_prompt_bindings (
        binding_id VARCHAR PRIMARY KEY,
        worker_uid VARCHAR NOT NULL,
        policy_id VARCHAR NOT NULL,
        binding_kind VARCHAR NOT NULL DEFAULT 'default'
            CHECK (binding_kind IN ('default', 'override', 'fallback')),
        priority INTEGER NOT NULL DEFAULT 100,
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (worker_uid, policy_id, binding_kind)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_worker_prompt_bindings_lookup
        ON main.worker_prompt_bindings (worker_uid, active, priority)
    """,
    """
    CREATE TABLE IF NOT EXISTS main.tool_policy_directives (
        directive_id VARCHAR PRIMARY KEY,
        tool_name VARCHAR NOT NULL,
        policy_id VARCHAR NOT NULL,
        scope VARCHAR NOT NULL DEFAULT 'global'
            CHECK (scope IN ('global', 'worker', 'tenant', 'project')),
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (tool_name, policy_id, scope)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_tool_policy_directives_lookup
        ON main.tool_policy_directives (tool_name, scope, active)
    """,
]

_M017_WORKER_RUNTIME_POLICIES = [
    """
    CREATE TABLE IF NOT EXISTS main.worker_runtime_policies (
        runtime_policy_id VARCHAR PRIMARY KEY,
        worker_uid VARCHAR NOT NULL,
        policy_key VARCHAR NOT NULL,
        policy_scope VARCHAR NOT NULL DEFAULT 'runtime'
            CHECK (policy_scope IN ('identity', 'category', 'capability', 'tool_policy', 'flag', 'behavior', 'runtime')),
        policy_value_json TEXT NOT NULL DEFAULT '{}'
            CHECK (json_valid(policy_value_json)),
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (worker_uid, policy_key, policy_scope)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_worker_runtime_policies_lookup
        ON main.worker_runtime_policies (worker_uid, active, policy_scope, policy_key)
    """,
]

_M018_AUTHORIZED_USERS = [
    """
    CREATE TABLE IF NOT EXISTS main.authorized_users (
        tenant_id VARCHAR,
        user_id VARCHAR,
        username VARCHAR,
        role VARCHAR DEFAULT 'user',
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tenant_id, user_id)
    )
    """,
]

_M019_MANAGED_WORKSPACE_DRAFT_POLICY = [
    """
    INSERT INTO main.prompt_policy_registry
      (policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active)
    SELECT
      'ppol_admin_workspace_managed_draft_v1',
      'manager_task',
      'admin_workspace_managed_draft',
      1,
      'active',
      content,
      sha256(content),
      '{"seed":"schema_migration_019","scope":"admin_workspace"}',
      true
    FROM (
      SELECT '{"draft_prompt_template":"Responde SOLO JSON válido, sin markdown, sin texto extra.\\nNo inventes secretos. No escribas en DB. Solo prepara un borrador revisable.\\nSchema exacto:\\n{{\\"project\\":{{\\"name\\":\\"string\\",\\"description\\":\\"string\\"}},\\"workers\\":[{{\\"worker_id\\":\\"string\\",\\"display_name\\":\\"string\\",\\"role\\":\\"member\\",\\"system_prompt\\":\\"string\\"}}],\\"shared_context\\":\\"markdown string\\",\\"suggested_skills\\":[{{\\"name\\":\\"string\\",\\"reason\\":\\"string\\",\\"available\\":true}}],\\"questions\\":[\\"string\\"]}}\\nSkills detectadas o sugeridas: {suggested_skills_json}\\nObjetivo del usuario:\\n{prompt}","fallback":{"project_name_template":"{title}","project_description_template":"Proyecto orientado a convertir el objetivo {goal} en un flujo DB-first con contexto, workers sugeridos y pasos de validación antes de ejecutar cambios.","worker_id_template":"{slug}-agent","worker_display_name_template":"Asistente {project_name}","worker_role":"member","system_prompt_template":"Actúa como asistente especializado del proyecto {project_name}. Usa el contexto compartido, convierte objetivos en pasos verificables y pregunta antes de asumir datos faltantes.","shared_context_template":"# Análisis del proyecto\\n\\n## Lectura del objetivo\\n{prompt}\\n\\n## Supuestos iniciales\\n- El proyecto debe operar con configuración DB-first.\\n- El usuario revisará el borrador antes de persistir cambios.\\n- Los workers sugeridos deben pedir datos faltantes antes de actuar.","model_error_note_template":"> Nota: no se pudo invocar el modelo configurado; se usó análisis local estructurado.","questions":["¿Qué fuentes de datos debe usar este proyecto?","¿Qué resultado concreto esperas del worker principal?","¿Hay restricciones de tono, seguridad o aprobación humana?"]},"confirm":{"source_kind":"managed_draft","context_title":"Contexto compartido","change_note":"Creado desde flujo administrado DB-first"}}' AS content
    )
    WHERE NOT EXISTS (
      SELECT 1
      FROM main.prompt_policy_registry
      WHERE policy_type = 'manager_task'
        AND policy_name = 'admin_workspace_managed_draft'
        AND version = 1
    )
    """,
]

_M020_FRAMEWORK_CAPABILITY_POLICIES = [
    """
    INSERT INTO main.prompt_policy_registry
      (policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active)
    SELECT
      'ppol_capability_generic_worker_v1',
      'capability',
      'generic_worker',
      1,
      'active',
      content,
      sha256(content),
      '{"seed":"schema_migration_020","scope":"framework"}',
      true
    FROM (
      SELECT 'Como agente {worker_id} puedo conversar, consultar DuckDB (solo lectura cuando aplica), usar herramientas del manifest y coordinar subtareas. Indica tu objetivo de forma concreta.' AS content
    )
    WHERE NOT EXISTS (
      SELECT 1
      FROM main.prompt_policy_registry
      WHERE policy_type = 'capability'
        AND policy_name = 'generic_worker'
        AND version = 1
    )
    """,
    """
    INSERT INTO main.prompt_policy_registry
      (policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active)
    SELECT
      'ppol_capability_axis_coordinator_v1',
      'capability',
      'axis_coordinator',
      1,
      'active',
      content,
      sha256(content),
      '{"seed":"schema_migration_020","scope":"framework"}',
      true
    FROM (
      SELECT 'Coordino el equipo desde {coord}. Agentes disponibles:\n{lines}\nIndica qué agente o tarea necesitas.' AS content
    )
    WHERE NOT EXISTS (
      SELECT 1
      FROM main.prompt_policy_registry
      WHERE policy_type = 'capability'
        AND policy_name = 'axis_coordinator'
        AND version = 1
    )
    """,
    """
    INSERT INTO main.prompt_policy_registry
      (policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active)
    SELECT
      'ppol_capability_default_fallback_v1',
      'capability',
      'default_fallback',
      1,
      'active',
      content,
      sha256(content),
      '{"seed":"schema_migration_020","scope":"framework"}',
      true
    FROM (
      SELECT 'Puedo ayudarte con conversación general, consultas DuckDB y herramientas configuradas en tu entorno. Escribe qué necesitas con detalle.' AS content
    )
    WHERE NOT EXISTS (
      SELECT 1
      FROM main.prompt_policy_registry
      WHERE policy_type = 'capability'
        AND policy_name = 'default_fallback'
        AND version = 1
    )
    """,
    """
    INSERT INTO main.prompt_policy_registry
      (policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active)
    SELECT
      'ppol_system_prompt_default_v1',
      'system_prompt',
      'default',
      1,
      'active',
      content,
      sha256(content),
      '{"seed":"schema_migration_020","scope":"framework"}',
      true
    FROM (
      SELECT 'Eres un asistente útil con acceso a una base de datos DuckDB y a un sandbox de ejecución Python/Bash. Cuando uses una herramienta, interpreta el resultado y responde en lenguaje natural claro y conciso. Nunca copies el resultado crudo de una herramienta. Si hay una lista de tablas, menciónalas de forma legible. Si hay datos de una consulta, preséntelos de forma organizada. Usa run_sandbox para ejecutar código Python o Bash arbitrario cuando el usuario lo pida. Estilo de respuesta: sé conciso y directo; usa como máximo 1 o 2 emojis por mensaje si aportan claridad; evita listas largas sin resumir, encabezados markdown (##) y relleno; responde con lo esencial.' AS content
    )
    WHERE NOT EXISTS (
      SELECT 1
      FROM main.prompt_policy_registry
      WHERE policy_type = 'system_prompt'
        AND policy_name = 'default'
        AND version = 1
    )
    """,
]

_M021_FRAMEWORK_POLICY_PACK = [
    "SELECT 1 AS framework_policy_pack_v1_noop",
]

_M022_FRAMEWORK_PACK_REFRESH = [
    "SELECT 1 AS framework_pack_refresh_v2_noop",
]

_M023_REPORT_ENGINE = [
    """
    CREATE TABLE IF NOT EXISTS main.admin_report_templates (
        template_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL,
        owner_email VARCHAR NOT NULL,
        name VARCHAR NOT NULL,
        description TEXT DEFAULT '',
        template_uri TEXT NOT NULL,
        section_schema_json TEXT NOT NULL DEFAULT '[]'
            CHECK (json_valid(section_schema_json)),
        analyzer_mode VARCHAR NOT NULL DEFAULT 'jinja'
            CHECK (analyzer_mode IN ('jinja', 'headings', 'mixed')),
        visibility VARCHAR NOT NULL DEFAULT 'private'
            CHECK (visibility IN ('private', 'tenant')),
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_report_templates_tenant
        ON main.admin_report_templates (tenant_id, owner_email, active)
    """,
    """
    CREATE TABLE IF NOT EXISTS main.admin_report_instances (
        instance_id VARCHAR PRIMARY KEY,
        template_id VARCHAR NOT NULL,
        tenant_id VARCHAR NOT NULL,
        owner_email VARCHAR NOT NULL,
        project_id VARCHAR DEFAULT '',
        title VARCHAR NOT NULL,
        period_key VARCHAR DEFAULT '',
        state_json TEXT NOT NULL DEFAULT '{"sections":{}}'
            CHECK (json_valid(state_json)),
        status VARCHAR NOT NULL DEFAULT 'draft'
            CHECK (status IN ('draft', 'ready', 'archived')),
        preview_html TEXT DEFAULT '',
        rendered_docx_uri TEXT DEFAULT '',
        conversation_id VARCHAR DEFAULT '',
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_report_instances_scope
        ON main.admin_report_instances (tenant_id, owner_email, project_id, status)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_report_instances_template
        ON main.admin_report_instances (template_id, period_key)
    """,
]


_M024_FRAMEWORK_REPORT_ENGINE_POLICY = [
    "SELECT 1 AS framework_report_engine_policy_noop",
]


_M025_FRAMEWORK_REPORT_ENGINE_TOOL_ROUTING = [
    "SELECT 1 AS framework_report_engine_tool_routing_noop",
]


_M026_FRAMEWORK_DOCUMENT_LANES = [
    "SELECT 1 AS framework_document_lanes_noop",
]

_M027_MCP_CONNECTORS = [
    """
    CREATE TABLE IF NOT EXISTS main.admin_mcp_connectors (
        connector_id VARCHAR PRIMARY KEY,
        tenant_id VARCHAR NOT NULL DEFAULT 'default',
        owner_email VARCHAR NOT NULL,
        display_name VARCHAR NOT NULL,
        transport VARCHAR NOT NULL,
        endpoint_url VARCHAR,
        launch_command VARCHAR,
        launch_args_json VARCHAR DEFAULT '[]',
        launch_env_json VARCHAR DEFAULT '{}',
        auth_kind VARCHAR NOT NULL DEFAULT 'none',
        auth_secret_key VARCHAR,
        tool_allowlist_json VARCHAR DEFAULT '[]',
        tool_denylist_json VARCHAR DEFAULT '[]',
        read_only BOOLEAN NOT NULL DEFAULT true,
        egress_hosts_json VARCHAR DEFAULT '[]',
        preset_id VARCHAR,
        enabled BOOLEAN NOT NULL DEFAULT true,
        active BOOLEAN NOT NULL DEFAULT true,
        metadata_json VARCHAR DEFAULT '{}',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_mcp_connectors_tenant
        ON main.admin_mcp_connectors (tenant_id, active, enabled)
    """,
    """
    CREATE TABLE IF NOT EXISTS main.admin_worker_mcp_grants (
        worker_uid VARCHAR NOT NULL,
        connector_id VARCHAR NOT NULL,
        permission VARCHAR NOT NULL DEFAULT 'use',
        active BOOLEAN NOT NULL DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (worker_uid, connector_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_worker_mcp_grants_connector
        ON main.admin_worker_mcp_grants (connector_id, active)
    """,
]


_M028_SKILL_CATALOG = [
    """
    CREATE TABLE IF NOT EXISTS main.admin_skill_categories (
        category_id VARCHAR PRIMARY KEY,
        category_key VARCHAR NOT NULL UNIQUE,
        title VARCHAR NOT NULL,
        description TEXT,
        sort_order INTEGER DEFAULT 0,
        read_only BOOLEAN DEFAULT false,
        scope VARCHAR DEFAULT 'platform',
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS main.admin_skill_catalog_items (
        item_id VARCHAR PRIMARY KEY,
        category_id VARCHAR NOT NULL,
        skill_key VARCHAR NOT NULL,
        label VARCHAR NOT NULL,
        hint TEXT,
        sort_order INTEGER DEFAULT 0,
        default_config_json TEXT DEFAULT '{}',
        active BOOLEAN DEFAULT true,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (category_id, skill_key)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_admin_skill_catalog_items_category
        ON main.admin_skill_catalog_items (category_id, active, sort_order)
    """,
]


_M030_USER_AGENT_DRAFT_POLICY = [
    """
    INSERT INTO main.prompt_policy_registry
      (policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active)
    SELECT
      'ppol_admin_user_agent_draft_v1',
      'manager_task',
      'admin_user_agent_draft',
      1,
      'active',
      content,
      sha256(content),
      '{"seed":"schema_migration_030","scope":"admin_user_agent"}',
      true
    FROM (
      SELECT '{"draft_prompt_template":"Responde SOLO JSON válido, sin markdown, sin texto extra.\\nNo inventes secretos. No escribas en DB. Solo prepara un borrador revisable de un agente runtime.\\nSchema exacto:\\n{{\\"display_name\\":\\"string\\",\\"worker_id\\":\\"string\\",\\"description\\":\\"string\\",\\"system_prompt\\":\\"string\\",\\"soul\\":\\"string\\",\\"tool_profile\\":\\"general|minimal|rag_only\\",\\"skills\\":[\\"string\\"],\\"browser_sandbox\\":false,\\"web_search\\":false,\\"suggested_skills\\":[{{\\"name\\":\\"string\\",\\"reason\\":\\"string\\",\\"available\\":true}}],\\"questions\\":[\\"string\\"]}}\\nHints opcionales: display_name={display_name_hint}, worker_id={worker_id_hint}\\nSkills detectadas o sugeridas: {suggested_skills_json}\\nComportamiento deseado del agente:\\n{prompt}","fallback":{"display_name_template":"Asistente {title}","worker_id_template":"{slug}-agent","description_template":"Agente orientado a: {goal}","system_prompt_template":"Eres un agente especializado. Tu misión es ayudar con: {goal}.\\n\\nReglas:\\n- Pide datos faltantes antes de asumir.\\n- Usa herramientas del manifest solo cuando aporten valor.\\n- Responde en español claro y accionable.","soul_template":"# Personalidad\\n- Profesional y directo\\n- Prioriza verificabilidad\\n\\n# Enfoque\\n{goal}","tool_profile":"general","skills":[],"browser_sandbox":false,"web_search":false,"model_error_note_template":"> Nota: no se pudo invocar el modelo configurado; se usó análisis local estructurado.","questions":["¿Qué resultado concreto debe entregar este agente?","¿Qué fuentes de datos o herramientas debe usar?","¿Hay restricciones de tono, seguridad o aprobación humana?"]}}' AS content
    )
    WHERE NOT EXISTS (
      SELECT 1
      FROM main.prompt_policy_registry
      WHERE policy_type = 'manager_task'
        AND policy_name = 'admin_user_agent_draft'
        AND version = 1
    )
    """,
]


def _migration_024_framework_report_engine_policy(db: Any) -> None:
    from duckclaw.framework_policy_pack import apply_framework_policy_pack

    apply_framework_policy_pack(db)


def _migration_025_framework_report_engine_tool_routing(db: Any) -> None:
    from duckclaw.framework_policy_pack import apply_framework_policy_pack

    apply_framework_policy_pack(db)


def _migration_026_framework_document_lanes(db: Any) -> None:
    from duckclaw.framework_policy_pack import apply_framework_policy_pack

    apply_framework_policy_pack(db)


def _migration_021_apply_framework_policy_pack(db: Any) -> None:
    from duckclaw.framework_policy_pack import apply_framework_policy_pack

    apply_framework_policy_pack(db)


def _migration_022_refresh_framework_packs(db: Any) -> None:
    from duckclaw.framework_policy_pack import apply_framework_policy_pack

    apply_framework_policy_pack(db)


def _migration_028_seed_skill_catalog(db: Any) -> None:
    from duckclaw.skill_catalog import seed_framework_skill_catalog_if_empty

    seed_framework_skill_catalog_if_empty(db)


def _migration_029_sync_skill_catalog_github_mcp(db: Any) -> None:
    from duckclaw.skill_catalog import sync_framework_skill_catalog_from_pack

    sync_framework_skill_catalog_from_pack(db)


_MIGRATION_HOOKS: dict[int, MigrationHook] = {
    21: _migration_021_apply_framework_policy_pack,
    22: _migration_022_refresh_framework_packs,
    24: _migration_024_framework_report_engine_policy,
    25: _migration_025_framework_report_engine_tool_routing,
    26: _migration_026_framework_document_lanes,
    28: _migration_028_seed_skill_catalog,
    29: _migration_029_sync_skill_catalog_github_mcp,
}

_ALL_MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (1, "initial_core", _M001_INITIAL_CORE),
    (2, "worker_versions", _M002_WORKER_VERSIONS),
    (3, "worker_contexts", _M003_WORKER_CONTEXTS),
    (4, "assignments", _M004_ASSIGNMENTS),
    (5, "skills_and_capabilities", _M005_SKILLS_AND_CAPS),
    (6, "projects", _M006_PROJECTS),
    (7, "runtime_settings", _M007_RUNTIME_SETTINGS),
    (8, "resources", _M008_RESOURCES),
    (9, "shared_db_grants", _M009_SHARED_DB_GRANTS),
    (10, "write_ledger", _M010_WRITE_LEDGER),
    (11, "conversations", _M011_CONVERSATIONS),
    (12, "kanban", _M012_KANBAN),
    (13, "workflows", _M013_WORKFLOWS),
    (14, "tools", _M014_TOOLS),
    (15, "knowledge", _M015_KNOWLEDGE),
    (16, "prompt_policies", _M016_PROMPT_POLICIES),
    (17, "worker_runtime_policies", _M017_WORKER_RUNTIME_POLICIES),
    (18, "authorized_users", _M018_AUTHORIZED_USERS),
    (19, "managed_workspace_draft_policy", _M019_MANAGED_WORKSPACE_DRAFT_POLICY),
    (20, "framework_capability_policies", _M020_FRAMEWORK_CAPABILITY_POLICIES),
    (21, "framework_policy_pack_v1", _M021_FRAMEWORK_POLICY_PACK),
    (22, "framework_pack_refresh_v2", _M022_FRAMEWORK_PACK_REFRESH),
    (23, "report_engine_v1", _M023_REPORT_ENGINE),
    (24, "framework_report_engine_policy", _M024_FRAMEWORK_REPORT_ENGINE_POLICY),
    (25, "framework_report_engine_tool_routing", _M025_FRAMEWORK_REPORT_ENGINE_TOOL_ROUTING),
    (26, "framework_document_lanes", _M026_FRAMEWORK_DOCUMENT_LANES),
    (27, "mcp_connectors_v1", _M027_MCP_CONNECTORS),
    (28, "skill_catalog_v1", _M028_SKILL_CATALOG),
    (29, "skill_catalog_github_mcp", []),
    (30, "user_agent_draft_policy", _M030_USER_AGENT_DRAFT_POLICY),
]
