"""Worker routing helpers for the manager graph.

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
    from duckclaw.graphs.manager_graph import clear_worker_graph_cache as _clear_worker_graph_cache

    _clear_worker_graph_cache()


def _worker_id_alnum_slug(worker_id: str | None) -> str:
    """Normaliza id de plantilla (guiones Unicode, espacios) para ramas por worker."""
    return re.sub(r"[^a-z0-9]", "", (worker_id or "").lower())


def _is_job_hunter_worker(worker_id: str | None) -> bool:
    """True si el id de plantilla corresponde a OSINT JobHunter (carpeta Job-Hunter o id job_hunter)."""
    w = (worker_id or "").strip()
    if not w:
        return False
    if _worker_id_alnum_slug(w) == "jobhunter":
        return True
    norm = w.lower()
    for ch in ("\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2212", "\uff0d"):
        norm = norm.replace(ch, "-")
    norm = norm.replace("_", "-").strip("-")
    return norm == "job-hunter"


def _worker_matches_id(worker_id: str | None, alias: str | None) -> bool:
    """Compara ids de worker tolerando guiones/underscores/case."""
    return _worker_id_alnum_slug(worker_id) == _worker_id_alnum_slug(alias)


def _pick_job_hunter_worker(available_templates: list[str]) -> str | None:
    """Retorna el worker JobHunter presente en el team efectivo."""
    for wid in available_templates or []:
        if _is_job_hunter_worker(wid):
            return wid
    return None


def _finanz_worker_in_templates(available_templates: list[str]) -> bool:
    """True si el equipo incluye al worker finanz (A2A Manager -> Finanz -> JobHunter -> Finanz)."""
    for wid in available_templates or []:
        if _worker_matches_id(wid, "finanz"):
            return True
    return False


def _pick_quant_trader_worker(available_templates: list[str]) -> str | None:
    for wid in available_templates or []:
        if _worker_matches_id(wid, "quant_trader"):
            return wid
    return None


__all__ = [
    "_LONE_HTTP_URL_ONLY_LINE",
    "_finanz_worker_in_templates",
    "_is_job_hunter_worker",
    "_pick_job_hunter_worker",
    "_pick_quant_trader_worker",
    "_worker_id_alnum_slug",
    "_worker_matches_id",
    "clear_worker_graph_cache",
]

