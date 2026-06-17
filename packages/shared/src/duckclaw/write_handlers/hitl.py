"""DB-writer handlers for transversal HITL tables."""

from __future__ import annotations

from typing import Any


def _ensure_code_decisions_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS main.code_decisions (
            id VARCHAR PRIMARY KEY,
            repo VARCHAR,
            file_path VARCHAR,
            branch_name VARCHAR,
            proposed_change TEXT,
            decision_type VARCHAR,
            title VARCHAR,
            rationale TEXT,
            status VARCHAR DEFAULT 'PENDING_HITL',
            pr_url VARCHAR,
            pr_number BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolved_by VARCHAR
        )
        """
    )


def _ensure_agent_uncertainty_log_table(conn: Any) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS main.agent_uncertainty_log (
            id VARCHAR PRIMARY KEY,
            session_uid VARCHAR,
            worker_id VARCHAR,
            trigger_context VARCHAR,
            confidence_score DOUBLE,
            description TEXT,
            proposed_questions JSON,
            status VARCHAR DEFAULT 'PENDING_HITL',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            resolved_by VARCHAR
        )
        """
    )


def _apply_update_code_decision_status(conn: Any, payload: dict) -> None:
    decision_id = str(payload.get("decision_id") or "").strip()
    status = str(payload.get("status") or "").strip().upper()
    if not decision_id:
        raise ValueError("decision_id required")
    if status not in {"APPROVED", "REJECTED", "FAILED"}:
        raise ValueError("invalid code decision status")

    _ensure_code_decisions_table(conn)
    pr_url = str(payload.get("pr_url") or "")[:2048]
    pr_number = payload.get("pr_number")
    rationale = str(payload.get("rationale") or "")[:8192]
    resolved_by = str(payload.get("resolved_by") or payload.get("actor_email") or "system")[:256]

    conn.execute(
        """
        UPDATE main.code_decisions
        SET status = ?,
            pr_url = COALESCE(NULLIF(?, ''), pr_url),
            pr_number = COALESCE(?, pr_number),
            rationale = COALESCE(NULLIF(?, ''), rationale),
            resolved_at = CURRENT_TIMESTAMP,
            resolved_by = ?
        WHERE id = ? AND status = 'PENDING_HITL'
        """,
        [status, pr_url, pr_number, rationale, resolved_by, decision_id],
    )


def _apply_resolve_uncertainty_event(conn: Any, payload: dict) -> None:
    event_id = str(payload.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("event_id required")

    resolved_by = str(payload.get("resolved_by") or payload.get("actor_email") or "system")[:256]
    _ensure_agent_uncertainty_log_table(conn)
    conn.execute(
        """
        UPDATE main.agent_uncertainty_log
        SET status = 'RESOLVED',
            resolved_at = CURRENT_TIMESTAMP,
            resolved_by = ?
        WHERE id = ? AND status = 'PENDING_HITL'
        """,
        [resolved_by, event_id],
    )


from duckclaw.write_handlers.registry import register_handler

register_handler("update_code_decision_status", _apply_update_code_decision_status)
register_handler("resolve_uncertainty_event", _apply_resolve_uncertainty_event)
