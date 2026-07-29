"""Pydantic models and TypedDict for the loop infrastructure thermostat."""

from __future__ import annotations

from typing import Any, Literal, NotRequired, TypedDict

from pydantic import BaseModel, Field

CorrectiveActionType = Literal[
    "purge_stale_tasks",
    "quarantine_corrupted_memory",
    "request_compaction",
    "alert_admin",
    "circuit_breaker_pause",
    "noop",
]

MeditateRunStatus = Literal[
    "pending",
    "sweeping",
    "calculating",
    "planning",
    "dispatching",
    "completed",
    "failed",
]

DEFAULT_STALE_TASK_SOURCE_TABLE = "main.task_audit_log"
DEFAULT_STALE_TASK_SOURCES: tuple[str, ...] = (
    DEFAULT_STALE_TASK_SOURCE_TABLE,
)


class HomeostasisTarget(BaseModel):
    """Per-tenant infrastructure homeostasis targets (persisted in main.homeostasis_targets)."""

    error_rate_pct: float = Field(default=2.0, ge=0)
    stale_tasks_count: int = Field(default=0, ge=0)
    memory_fragmentation_index: float = Field(default=0.15, ge=0, le=1)
    avg_latency_ms: float = Field(default=5000.0, ge=0)
    db_lock_events: int = Field(default=0, ge=0)
    stale_task_sources: list[str] = Field(default_factory=lambda: list(DEFAULT_STALE_TASK_SOURCES))


class DomainGoal(BaseModel):
    """Domain goal contrasted by /loop alongside infra metrics."""

    belief_key: str
    target_value: float
    threshold: float
    # task: goal discrete / can be "satisfied" via evidence + HITL.
    # monitor: continuous objective; still participates in alignment deviations.
    goal_kind: Literal["task", "monitor"] = "task"
    title: str = ""
    observed_value: float | None = None
    # pct | usd | raw — how target_value/threshold are expressed (default: no conversion).
    target_unit: Literal["pct", "usd", "raw"] = "raw"
    # Opaque session-settings key for pct conversion (required when target_unit == "pct").
    anchor_setting_key: str = ""
    # Lower number = higher priority (P1 before P2). Agent should address in this order.
    priority: int = Field(default=100, ge=1)


class HomeostasisManifest(BaseModel):
    """Single source of truth: infra thresholds + domain goals for /loop contrast."""

    infra: HomeostasisTarget = Field(default_factory=HomeostasisTarget)
    goals: list[DomainGoal] = Field(default_factory=list)


class CurrentMetrics(BaseModel):
    error_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    stale_tasks_count: int = 0
    memory_fragmentation_index: float = 0.0
    db_lock_events: int = 0


class CorrectiveAction(BaseModel):
    action_type: CorrectiveActionType
    requires_hitl: bool = False
    reason: str = ""
    params: dict[str, Any] = Field(default_factory=dict)


class LoopState(TypedDict, total=False):
    """LangGraph state for loop runs."""

    run_id: str
    tenant_id: str
    worker_id: str
    chat_id: str
    vault_db_path: str
    user_id: str
    delta_interval_seconds: int
    status: MeditateRunStatus
    targets: dict[str, Any]
    domain_goals: list[dict[str, Any]]
    alignment_message: str
    current_metrics: dict[str, Any]
    distance_vector: dict[str, float]
    planned_actions: list[dict[str, Any]]
    dispatched_actions: list[dict[str, Any]]
    error: str
    admin_chat_id: str
    stale_task_ids: NotRequired[list[str]]
    memory_ids_to_quarantine: NotRequired[list[str]]


MeditateState = LoopState  # deprecated alias
