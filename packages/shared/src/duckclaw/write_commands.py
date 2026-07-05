"""Typed write commands for admin operations.

Replaces raw SQL on the Redis write queue with validated Pydantic commands.
Backward-compatible: raw ``admin_sql`` still works via the legacy path.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Literal

from pydantic import BaseModel, Field


class WriteCommand(BaseModel):
    """Base command for admin write operations. Every command has a unique task_id
    for idempotency (dedup in writer)."""

    command_type: str
    command_version: int = 1
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str = "default"
    actor_email: str = "system"

    def to_redis_payload(self) -> str:
        """Serialize command to JSON for LPUSH into the write queue."""
        return self.model_dump_json()


# ---------------------------------------------------------------------------
# Worker commands
# ---------------------------------------------------------------------------

class UpsertWorkerCommand(WriteCommand):
    """Create or update a worker in the catalog. Idempotent by worker_id + tenant_id."""

    command_type: Literal["upsert_worker"] = "upsert_worker"
    worker_id: str
    display_name: str
    source_kind: str = "runtime"
    source_template_id: str = "default"
    visibility: str = "private"
    system_prompt: str = ""
    manifest_snapshot: dict[str, Any] = Field(default_factory=dict)
    files_snapshot: dict[str, str] = Field(default_factory=dict)


class UpsertUserAgentCommand(WriteCommand):
    """Create or update an admin-owned runtime agent without filesystem writes."""

    command_type: Literal["upsert_user_agent"] = "upsert_user_agent"
    worker_uid: str = ""
    worker_id: str
    display_name: str
    source_template_id: str = "default"
    system_prompt: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    soul: str = ""
    tool_profile: str = "general"
    browser_sandbox: bool = False
    web_search: bool = False


class UpsertCatalogSkillCommand(WriteCommand):
    """Create or update one admin catalog skill through the singleton writer."""

    command_type: Literal["upsert_catalog_skill"] = "upsert_catalog_skill"
    name: str = Field(..., min_length=2, max_length=128)
    description: str = Field(default="", max_length=1024)
    skill_type: str = Field(default="python", max_length=64)
    implementation_ref: str = Field(..., min_length=3, max_length=512)
    visibility: Literal["private", "public"] = "private"


class DeactivateCatalogSkillCommand(WriteCommand):
    """Soft-delete one admin catalog skill by tenant, owner and name."""

    command_type: Literal["deactivate_catalog_skill"] = "deactivate_catalog_skill"
    name: str = Field(..., min_length=2, max_length=128)


class HardDeleteCatalogSkillCommand(WriteCommand):
    """Physically remove one admin catalog skill and worker attachments."""

    command_type: Literal["hard_delete_catalog_skill"] = "hard_delete_catalog_skill"
    name: str = Field(..., min_length=2, max_length=128)


class DeactivateWorkerCommand(WriteCommand):
    """Soft-delete a worker from the catalog."""

    command_type: Literal["deactivate_worker"] = "deactivate_worker"
    worker_id: str


class UpdateCatalogWorkerFileCommand(WriteCommand):
    """Update one DB-backed catalog worker file snapshot through the writer."""

    command_type: Literal["update_catalog_worker_file"] = "update_catalog_worker_file"
    worker_id: str
    file_path: str
    content: str = ""


class DeactivateCatalogWorkerCommand(WriteCommand):
    """Soft-delete an actor-owned catalog worker through the writer."""

    command_type: Literal["deactivate_catalog_worker"] = "deactivate_catalog_worker"
    worker_id: str


class ReactivateCatalogWorkerCommand(WriteCommand):
    """Reactivate an actor-owned catalog worker through the writer."""

    command_type: Literal["reactivate_catalog_worker"] = "reactivate_catalog_worker"
    worker_id: str


class HardDeleteCatalogWorkerCommand(WriteCommand):
    """Physically remove an actor-owned catalog worker and scoped relations."""

    command_type: Literal["hard_delete_catalog_worker"] = "hard_delete_catalog_worker"
    worker_id: str


class ImportTemplatesToCatalogCommand(WriteCommand):
    """Import filesystem worker templates into the DB catalog."""

    command_type: Literal["import_templates_to_catalog"] = "import_templates_to_catalog"
    templates_root: str
    include_prefixes: list[str] = Field(default_factory=list)
    include_template_ids: list[str] = Field(default_factory=list)


class UpsertWorkerContextCommand(WriteCommand):
    """Create a DB-first context row for an existing catalog worker."""

    command_type: Literal["upsert_worker_context"] = "upsert_worker_context"
    worker_uid: str
    title: str
    content_md: str = ""
    sort_order: int = 0


class ReorderWorkerContextsCommand(WriteCommand):
    """Update context ordering for one catalog worker."""

    command_type: Literal["reorder_worker_contexts"] = "reorder_worker_contexts"
    worker_uid: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class DeactivateWorkerContextCommand(WriteCommand):
    """Soft-delete one DB-first worker context."""

    command_type: Literal["deactivate_worker_context"] = "deactivate_worker_context"
    worker_uid: str
    context_id: str


class UpsertWorkerCapabilityCommand(WriteCommand):
    """Register and grant one DB-first capability to an existing catalog worker."""

    command_type: Literal["upsert_worker_capability"] = "upsert_worker_capability"
    worker_id: str
    capability_name: str
    kind: str = "runtime_policy"
    provider: str = "duckclaw"
    permission: str = "use"
    description: str = ""
    risk_level: str = "low"
    requires_secret: bool = False
    requires_network: bool = False
    capability_schema: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Project commands
# ---------------------------------------------------------------------------

class CreateProjectCommand(WriteCommand):
    """Create a project and optionally assign agents."""

    command_type: Literal["create_project"] = "create_project"
    project_id: str
    name: str
    description: str = ""
    visibility: str = "private"
    agent_worker_uids: list[str] = Field(default_factory=list)


class AddProjectMemberCommand(WriteCommand):
    """Add a member to a project."""

    command_type: Literal["add_project_member"] = "add_project_member"
    project_id: str
    member_email: str
    role: str = "member"


class AssignAgentToProjectCommand(WriteCommand):
    """Assign a catalog worker to a project."""

    command_type: Literal["assign_agent_to_project"] = "assign_agent_to_project"
    project_id: str
    worker_uid: str
    role: str = "member"
    sort_order: int = 0


class SetProjectStatusCommand(WriteCommand):
    """Set a reversible workspace project status."""

    command_type: Literal["set_project_status"] = "set_project_status"
    project_id: str
    status: Literal["active", "inactive"]


class DeleteProjectCommand(WriteCommand):
    """Hard-delete a workspace project and project-only relations."""

    command_type: Literal["delete_project"] = "delete_project"
    project_id: str


class DetachAgentFromProjectCommand(WriteCommand):
    """Soft-detach a catalog worker from a workspace project."""

    command_type: Literal["detach_agent_from_project"] = "detach_agent_from_project"
    project_id: str
    worker_uid: str


class ConfirmWorkspaceManagedDraftCommand(WriteCommand):
    """Confirm one managed workspace draft as one DB-writer transaction."""

    command_type: Literal["confirm_workspace_managed_draft"] = "confirm_workspace_managed_draft"
    project_id: str
    project_name: str
    project_description: str = ""
    workers: list[dict[str, Any]] = Field(default_factory=list)
    shared_context: str = ""
    suggested_skills: list[dict[str, Any]] = Field(default_factory=list)
    source_kind: str = "managed_draft"
    context_title: str = "Contexto compartido"
    change_note: str = "Created from DB-first managed draft"


# ---------------------------------------------------------------------------
# Runtime settings commands
# ---------------------------------------------------------------------------

class UpsertRuntimeSettingCommand(WriteCommand):
    """Create or update a runtime setting. Idempotent by domain + key + tenant."""

    command_type: Literal["upsert_runtime_setting"] = "upsert_runtime_setting"
    domain: str
    key: str
    value: str
    value_json: Any | None = None
    value_kind: str = "string"
    secret: bool = False
    updated_by: str = ""


class UpsertAgentConfigEntriesCommand(WriteCommand):
    """Upsert legacy agent_config entries through the singleton writer."""

    command_type: Literal["upsert_agent_config_entries"] = "upsert_agent_config_entries"
    entries: dict[str, str]


class DeleteAgentConfigEntriesCommand(WriteCommand):
    """Delete legacy agent_config entries through the singleton writer."""

    command_type: Literal["delete_agent_config_entries"] = "delete_agent_config_entries"
    keys: list[str]


class ForgetChatStateCommand(WriteCommand):
    """Delete one chat/session conversation history and audited chat state."""

    command_type: Literal["forget_chat_state"] = "forget_chat_state"
    chat_id: str


class AppendTaskAuditCommand(WriteCommand):
    """Append one row to the transversal task audit log used by /history."""

    command_type: Literal["append_task_audit"] = "append_task_audit"
    audit_task_id: str = Field(default_factory=lambda: f"TASK-{uuid.uuid4().hex[:16]}")
    worker_id: str = ""
    query_prefix: str = ""
    status: Literal["SUCCESS", "FAILED", "PROACTIVE_MESSAGE_SENT", "SECURITY_VIOLATION_ATTEMPT"] = "SUCCESS"
    duration_ms: int = 0
    plan_title: str = ""


class AppendLlmUsageLogCommand(WriteCommand):
    """Append one row to ``llm_usage_log`` with parameterized INSERT."""

    command_type: Literal["append_llm_usage_log"] = "append_llm_usage_log"
    id: str
    session_id: str = ""
    worker_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float = 0.0
    model: str = ""


class AppendMediaUsageLogCommand(WriteCommand):
    """Append one row to ``media_usage_log`` with parameterized INSERT."""

    command_type: Literal["append_media_usage_log"] = "append_media_usage_log"
    id: str
    session_id: str = ""
    worker_id: str = ""
    provider: str = "fal"
    model_endpoint: str = ""
    media_type: str = "image"
    cost_usd: float = 0.0
    latency_sec: float = 0.0
    media_url: str = ""


# ---------------------------------------------------------------------------
# Admin console user commands
# ---------------------------------------------------------------------------

class UpsertConsoleUserCommand(WriteCommand):
    """Create or update an admin console user."""

    command_type: Literal["upsert_console_user"] = "upsert_console_user"
    email: str
    nombre: str = ""
    rol: Literal["admin", "user", "viewer"] = "user"
    password: str | None = None
    initials: str = ""
    active: bool = True


class DeactivateConsoleUserCommand(WriteCommand):
    """Deactivate an admin console user."""

    command_type: Literal["deactivate_console_user"] = "deactivate_console_user"
    email: str


class RecordAdminLoginFailureCommand(WriteCommand):
    """Increment failed login tracking for one admin console user."""

    command_type: Literal["record_admin_login_failure"] = "record_admin_login_failure"
    email: str


class ClearAdminLoginFailuresCommand(WriteCommand):
    """Clear failed login tracking after a successful admin login."""

    command_type: Literal["clear_admin_login_failures"] = "clear_admin_login_failures"
    email: str


class UpdateConsoleUserPasswordHashCommand(WriteCommand):
    """Persist a verified password hash migration for one console user."""

    command_type: Literal["update_console_user_password_hash"] = "update_console_user_password_hash"
    email: str
    password_hash: str
    hash_algo: Literal["argon2id", "pbkdf2_sha256"] = "argon2id"
    hash_params: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Team access commands
# ---------------------------------------------------------------------------

class UpsertAuthorizedUserCommand(WriteCommand):
    """Create or update a Telegram Guard authorized user."""

    command_type: Literal["upsert_authorized_user"] = "upsert_authorized_user"
    user_id: str
    username: str = "Usuario"
    role: Literal["admin", "user"] = "user"


class DeleteAuthorizedUserCommand(WriteCommand):
    """Remove a Telegram Guard authorized user from a tenant whitelist."""

    command_type: Literal["delete_authorized_user"] = "delete_authorized_user"
    user_id: str


class UpsertSharedDbGrantCommand(WriteCommand):
    """Grant a Telegram user access to a shared DuckDB resource key."""

    command_type: Literal["upsert_shared_db_grant"] = "upsert_shared_db_grant"
    user_id: str
    resource_key: str


class DeleteSharedDbGrantCommand(WriteCommand):
    """Revoke a Telegram user's shared DuckDB resource key."""

    command_type: Literal["delete_shared_db_grant"] = "delete_shared_db_grant"
    user_id: str
    resource_key: str


# ---------------------------------------------------------------------------
# Kanban commands
# ---------------------------------------------------------------------------

class UpsertKanbanCardCommand(WriteCommand):
    """Create or update a DB-first Kanban card. Idempotent by card_id."""

    command_type: Literal["upsert_kanban_card"] = "upsert_kanban_card"
    card_id: str = Field(default_factory=lambda: f"card_{uuid.uuid4().hex[:16]}")
    title: str
    description: str = ""
    status: Literal["todo", "in_progress", "done", "cancelled"] = "todo"
    priority: int = 0
    sort_order: int = 0
    worker_id: str = ""
    tags: list[str] = Field(default_factory=list)


class DeleteKanbanCardCommand(WriteCommand):
    """Delete a DB-first Kanban card scoped to tenant + actor."""

    command_type: Literal["delete_kanban_card"] = "delete_kanban_card"
    card_id: str


# ---------------------------------------------------------------------------
# Knowledge/RAG commands
# ---------------------------------------------------------------------------

class CreateKnowledgeSourceCommand(WriteCommand):
    """Create or update a transversal RAG knowledge source."""

    command_type: Literal["create_knowledge_source"] = "create_knowledge_source"
    source_id: str = Field(default_factory=lambda: f"ksrc_{uuid.uuid4().hex[:16]}")
    project_id: str = ""
    worker_uid: str = ""
    source_kind: Literal["folder", "file", "url", "manual", "api"] = "folder"
    source_uri: str
    display_name: str = ""
    status: Literal["pending", "indexing", "ready", "failed", "inactive"] = "pending"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpsertKnowledgeDocumentCommand(WriteCommand):
    """Create or update a normalized document within a knowledge source."""

    command_type: Literal["upsert_knowledge_document"] = "upsert_knowledge_document"
    document_id: str = Field(default_factory=lambda: f"kdoc_{uuid.uuid4().hex[:16]}")
    source_id: str
    relative_path: str
    title: str = ""
    mime_type: str = "text/plain"
    checksum: str
    byte_size: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class UpsertKnowledgeChunksCommand(WriteCommand):
    """Replace a document's active RAG chunks with validated chunk payloads."""

    command_type: Literal["upsert_knowledge_chunks"] = "upsert_knowledge_chunks"
    document_id: str
    source_id: str
    project_id: str = ""
    worker_uid: str = ""
    chunks: list[dict[str, Any]] = Field(default_factory=list)


class DeactivateKnowledgeSourceCommand(WriteCommand):
    """Soft-delete a knowledge source and its derived documents/chunks."""

    command_type: Literal["deactivate_knowledge_source"] = "deactivate_knowledge_source"
    source_id: str


class DeactivateKnowledgeDocumentsCommand(WriteCommand):
    """Soft-delete specific documents (and their chunks) within a knowledge source."""

    command_type: Literal["deactivate_knowledge_documents"] = "deactivate_knowledge_documents"
    source_id: str
    document_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prompt policy commands
# ---------------------------------------------------------------------------

PromptPolicyType = Literal["directive", "capability", "system_prompt", "manager_task", "tool_directive"]
PromptPolicyStatus = Literal["draft", "active", "inactive", "archived"]


class UpsertPromptPolicyCommand(WriteCommand):
    """Create or update a DB-first prompt policy. Idempotent by type + name + version."""

    command_type: Literal["upsert_prompt_policy"] = "upsert_prompt_policy"
    policy_id: str = ""
    policy_type: PromptPolicyType
    policy_name: str
    version: int = 1
    status: PromptPolicyStatus = "active"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeactivatePromptPolicyCommand(WriteCommand):
    """Soft-delete one prompt policy version, or all versions for type + name."""

    command_type: Literal["deactivate_prompt_policy"] = "deactivate_prompt_policy"
    policy_type: PromptPolicyType
    policy_name: str
    version: int | None = None


class RestoreFrameworkPolicyPackCommand(WriteCommand):
    """Re-apply ``framework_policy_pack_v1`` via db-writer (no worker prompts)."""

    command_type: Literal["restore_framework_policy_pack"] = "restore_framework_policy_pack"
    force: bool = True
    actor_email: str = ""


class SyncCatalogPromptsCommand(WriteCommand):
    """Backfill ``system_prompt/<worker>`` from ``admin_worker_catalog`` snapshots."""

    command_type: Literal["sync_catalog_prompts"] = "sync_catalog_prompts"
    force: bool = False


# ---------------------------------------------------------------------------
# HITL commands
# ---------------------------------------------------------------------------

class UpdateCodeDecisionStatusCommand(WriteCommand):
    """Update one row in ``main.code_decisions`` after human approval/rejection."""

    command_type: Literal["update_code_decision_status"] = "update_code_decision_status"
    decision_id: str
    status: Literal["APPROVED", "REJECTED", "FAILED"]
    pr_url: str = ""
    pr_number: int | None = None
    rationale: str = ""
    resolved_by: str = "system"


class ResolveUncertaintyEventCommand(WriteCommand):
    """Resolve one ``main.agent_uncertainty_log`` event from PENDING_HITL."""

    command_type: Literal["resolve_uncertainty_event"] = "resolve_uncertainty_event"
    event_id: str
    session_uid: str = ""
    resolved_by: str = "system"


# ---------------------------------------------------------------------------
# DuckDB admin maintenance commands
# ---------------------------------------------------------------------------

class DropLegacyDuckDbObjectsCommand(WriteCommand):
    """Drop explicitly selected legacy DuckDB schemas or main tables."""

    command_type: Literal["drop_legacy_duckdb_objects"] = "drop_legacy_duckdb_objects"
    user_id: str = "default"
    db_path: str = ""
    schemas: list[str] = Field(default_factory=list)
    main_tables: list[str] = Field(default_factory=list)


class DeactivateMcpConnectorCommand(WriteCommand):
    """Soft-delete MCP connector and revoke grants."""

    command_type: Literal["deactivate_mcp_connector"] = "deactivate_mcp_connector"
    connector_id: str


class UpsertMcpConnectorCommand(WriteCommand):
    """Create or update MCP connector registry row."""

    command_type: Literal["upsert_mcp_connector"] = "upsert_mcp_connector"
    connector_id: str = ""
    display_name: str = ""
    transport: str = ""
    endpoint_url: str = ""
    launch_command: str = ""
    launch_args: list[str] = Field(default_factory=list)
    launch_env: dict[str, str] = Field(default_factory=dict)
    auth_kind: str = "none"
    tool_allowlist: list[str] = Field(default_factory=list)
    tool_denylist: list[str] = Field(default_factory=list)
    read_only: bool | None = None
    egress_hosts: list[str] = Field(default_factory=list)
    preset_id: str = ""
    enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class SetMcpConnectorAuthCommand(WriteCommand):
    """Store bearer token for remote MCP connector (secret runtime setting)."""

    command_type: Literal["set_mcp_connector_auth"] = "set_mcp_connector_auth"
    connector_id: str
    bearer_token: str


class GrantWorkerMcpConnectorCommand(WriteCommand):
    """Grant worker access to MCP connector tools."""

    command_type: Literal["grant_worker_mcp_connector"] = "grant_worker_mcp_connector"
    connector_id: str
    worker_uid: str
    permission: str = "use"


class RevokeWorkerMcpConnectorCommand(WriteCommand):
    """Revoke worker MCP connector grant."""

    command_type: Literal["revoke_worker_mcp_connector"] = "revoke_worker_mcp_connector"
    connector_id: str
    worker_uid: str


# ---------------------------------------------------------------------------
# Raw SQL (legacy — keep for admin_sql tool)
# ---------------------------------------------------------------------------

class RawSqlCommand(WriteCommand):
    """Legacy raw SQL command preserved for admin_sql tool compatibility.
    Prefer typed commands for structured operations."""

    command_type: Literal["raw_sql"] = "raw_sql"
    query: str
    params: list[Any] = Field(default_factory=list)
    db_path: str = ""
    user_id: str = "default"
