"""Transversal HITL service facade for code decisions and epistemic uncertainty."""

from __future__ import annotations

from typing import Any

from duckclaw.hitl.code_decision_service import approve_code_decision, reject_code_decision
from duckclaw.hitl.db_access import _query_rows, table_exists
from duckclaw.hitl.uncertainty_service import (
    list_pending_uncertainty_events,
    resolve_uncertainty_event,
)

_CODE_DECISIONS_TABLE = "code_decisions"


def hitl_mutation_unavailable_message() -> str:
    return (
        "Mutación HITL no disponible: el vault no expone ruta de DuckDB "
        "o el DB-writer no está accesible."
    )


def list_pending_code_decisions(
    db: Any,
    *,
    limit: int = 20,
    status: str = "PENDING_HITL",
) -> list[dict[str, Any]]:
    if not table_exists(db, _CODE_DECISIONS_TABLE):
        return []
    bounded = max(1, min(int(limit or 20), 100))
    st = (status or "PENDING_HITL").strip() or "PENDING_HITL"
    return _query_rows(
        db,
        """
        SELECT id, repo, file_path, branch_name, decision_type, title, status, created_at, pr_url
        FROM main.code_decisions
        WHERE status = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (st, bounded),
    )


__all__ = [
    "approve_code_decision",
    "hitl_mutation_unavailable_message",
    "list_pending_code_decisions",
    "list_pending_uncertainty_events",
    "reject_code_decision",
    "resolve_uncertainty_event",
]
