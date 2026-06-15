"""Compatibility facade for the manager LangGraph builder.

The implementation lives in ``duckclaw.manager.graph``. Keep this module so
legacy imports from ``duckclaw.graphs.manager_graph`` continue to work.
"""

from __future__ import annotations

from importlib import import_module as _import_module
from typing import Any as _Any

_manager_graph = _import_module("duckclaw.manager.graph")

_exported_names = [name for name in dir(_manager_graph) if not name.startswith("__")]
__all__ = [name for name in _exported_names if not name.startswith("_")]


def __getattr__(name: str) -> _Any:
    return getattr(_manager_graph, name)


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_exported_names))


globals().update({name: getattr(_manager_graph, name) for name in _exported_names})
