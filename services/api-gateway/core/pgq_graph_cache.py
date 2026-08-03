"""Disk cache paths for PGQ memory graph HTML exports (gateway install / duckclaw repo)."""

from __future__ import annotations

import hashlib
from pathlib import Path

_GATEWAY_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def pgq_repo_root() -> Path:
    return _GATEWAY_ROOT


def memory_graph_generator_script() -> Path:
    return pgq_repo_root() / "scripts" / "generate_memory_graph.py"


def graph_cache_dir() -> Path:
    return pgq_repo_root() / "data" / "graph-cache"


def vault_cache_key(vault_path: str) -> str:
    resolved = str(Path(vault_path).resolve())
    return hashlib.sha256(resolved.encode()).hexdigest()[:16]


def memory_graph_html_path(vault_path: str) -> Path:
    return graph_cache_dir() / vault_cache_key(vault_path) / "memory_graph.html"
