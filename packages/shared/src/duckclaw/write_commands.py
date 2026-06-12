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


class DeactivateWorkerCommand(WriteCommand):
    """Soft-delete a worker from the catalog."""

    command_type: Literal["deactivate_worker"] = "deactivate_worker"
    worker_id: str


# ---------------------------------------------------------------------------
# Project commands
# ---------------------------------------------------------------------------

class CreateProjectCommand(WriteCommand):
    """Create a project and optionally assign agents."""

    command_type: Literal["create_project"] = "create_project"
    project_id: str
    name: str
    description: str = ""
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


# ---------------------------------------------------------------------------
# Runtime settings commands
# ---------------------------------------------------------------------------

class UpsertRuntimeSettingCommand(WriteCommand):
    """Create or update a runtime setting. Idempotent by domain + key + tenant."""

    command_type: Literal["upsert_runtime_setting"] = "upsert_runtime_setting"
    domain: str
    key: str
    value: str
    value_kind: str = "string"
    secret: bool = False


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
