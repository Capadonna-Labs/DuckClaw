"""Generic worker routing helpers for the manager graph.

The graph still owns orchestration state, but pure worker-id routing helpers
live here so callers do not need to import the monolithic graph module.
"""

from __future__ import annotations

import re


_LONE_HTTP_URL_ONLY_LINE = re.compile(
    r"^\s*https?://[^\s]+\s*$",
    re.I,
)


def clear_worker_graph_cache() -> None:
    """Compatibility wrapper for callers that historically imported this facade."""
    from duckclaw.manager.manager_worker_cache import clear_worker_graph_cache as _clear

    _clear()


def _worker_id_alnum_slug(worker_id: str | None) -> str:
    """Normaliza ids de plantilla tolerando guiones Unicode, espacios y case."""
    return re.sub(r"[^a-z0-9]", "", (worker_id or "").lower())


def _worker_matches_id(worker_id: str | None, alias: str | None) -> bool:
    """Compara ids de worker tolerando guiones/underscores/case."""
    return _worker_id_alnum_slug(worker_id) == _worker_id_alnum_slug(alias)


__all__ = [
    "_LONE_HTTP_URL_ONLY_LINE",
    "_worker_id_alnum_slug",
    "_worker_matches_id",
    "clear_worker_graph_cache",
]

