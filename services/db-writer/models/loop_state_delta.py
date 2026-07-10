"""DTOs MEDITATE_STATE_DELTA (harness_core infrastructure mutations)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

MeditateDeltaType = Literal[
    "PURGE_STALE_TASKS",
    "QUARANTINE_MEMORY",
    "UPSERT_LOOP_AUDIT",
    "UPSERT_MEDITATE_AUDIT",
    "UPSERT_HOMEOSTASIS_MANIFEST",
]


class PurgeStaleTasksMutation(BaseModel):
    source_table: str = "main.task_audit_log"
    task_ids: list[str] = Field(default_factory=list)


class QuarantineMemoryMutation(BaseModel):
    memory_ids: list[str] = Field(default_factory=list)


class UpsertMeditateAuditMutation(BaseModel):
    run_id: str
    distance_vector: dict[str, float] = Field(default_factory=dict)
    actions_json: list[dict[str, Any]] = Field(default_factory=list)
    status: str = "completed"


class UpsertHomeostasisManifestMutation(BaseModel):
    manifest: dict[str, Any] = Field(default_factory=dict)


class LoopStateDelta(BaseModel):
    delta_type: MeditateDeltaType
    tenant_id: str = "default"
    user_id: str = "default"
    target_db_path: str
    mutation: dict[str, Any] = Field(default_factory=dict)

    def purge_mutation(self) -> PurgeStaleTasksMutation:
        return PurgeStaleTasksMutation.model_validate(self.mutation)

    def quarantine_mutation(self) -> QuarantineMemoryMutation:
        return QuarantineMemoryMutation.model_validate(self.mutation)

    def audit_mutation(self) -> UpsertMeditateAuditMutation:
        return UpsertMeditateAuditMutation.model_validate(self.mutation)

    def manifest_mutation(self) -> UpsertHomeostasisManifestMutation:
        return UpsertHomeostasisManifestMutation.model_validate(self.mutation)


MeditateStateDelta = LoopStateDelta
