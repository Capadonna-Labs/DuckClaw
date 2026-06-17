"""Thin re-export: LangGraph assembly for worker templates."""

from __future__ import annotations

from typing import Any

from duckclaw.workers.factory_graph_assembly import build_worker_graph as _build_worker_graph_impl


def build_worker_graph(*args: Any, **kwargs: Any) -> Any:
    return _build_worker_graph_impl(*args, **kwargs)


__all__ = ["build_worker_graph"]
