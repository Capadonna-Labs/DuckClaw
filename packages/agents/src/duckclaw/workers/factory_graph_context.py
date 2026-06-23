"""Shared context for worker LangGraph node factories."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional


@dataclass
class WorkerGraphContext:
    worker_id: str = ""
    db: Any = None
    spec: Any = None
    path: str = ""
    shared_resolved: str = ""
    provider: str = ""
    model: str = ""
    base_url: str = ""
    llm: Any = None
    llm_fallback: Any | None = None
    tool_surface: Literal["full", "context_synthesis", "visual_generation", "url_research"] = "full"
    tenant_id: str = "default"
    instance_name: Optional[str] = None
    system_prompt: str = ""
    effective_prompt: str = ""
    context_prompt_base: Optional[str] = None
    context_pruning: dict[str, Any] = field(default_factory=dict)
    use_context_monitor: bool = False
    logical_worker_id: str = ""
    prompt_policies: Any = None
    tools: list[Any] = field(default_factory=list)
    tools_by_name: dict[str, Any] = field(default_factory=dict)
    tools_sandbox_off: list[Any] = field(default_factory=list)
    tools_by_name_sandbox_off: dict[str, Any] = field(default_factory=dict)
    groq_bind: bool = False
    tools_for_llm_bind: list[Any] = field(default_factory=list)
    tools_sandbox_off_bind: list[Any] = field(default_factory=list)
    llm_summary: Any = None
    context_monitor_node: Any = None
    sandbox_enabled_for_state: Any = None
    agent_bind: dict[str, Any] = field(default_factory=dict)
    context_guard_enabled: bool = False
    context_guard_max_retries: int = 2
    max_tool_rounds: int = 10
    agent_turn: dict[str, Any] = field(default_factory=dict)
