"""Per-turn runtime for worker-to-worker ``invoke_worker`` tool."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class WorkerDelegateRuntime:
    db: Any
    llm: Any
    path: str
    spec: Any
    templates_root: Any
    tenant_id: str
    state: dict[str, Any]
    llm_provider: str = ""
    llm_model: str = ""
    llm_base_url: str = ""


_runtime: ContextVar[WorkerDelegateRuntime | None] = ContextVar(
    "duckclaw_worker_delegate_runtime",
    default=None,
)


def set_worker_delegate_runtime(runtime: WorkerDelegateRuntime | None) -> None:
    _runtime.set(runtime)


def get_worker_delegate_runtime() -> WorkerDelegateRuntime | None:
    return _runtime.get()


def clear_worker_delegate_runtime() -> None:
    _runtime.set(None)


__all__ = [
    "WorkerDelegateRuntime",
    "clear_worker_delegate_runtime",
    "get_worker_delegate_runtime",
    "set_worker_delegate_runtime",
]
