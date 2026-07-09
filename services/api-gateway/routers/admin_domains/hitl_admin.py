from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key
from routers.admin_domains.duckdb_explorer import _duckdb_readonly_session

router = APIRouter(tags=["admin-hitl"])


class AdminLoopTickBody(BaseModel):
    tenant_id: str = "default"
    worker_id: str
    vault_db_path: str = ""
    chat_id: str = "admin"
    delta_interval_seconds: int = Field(default=14400, ge=60)


class CodeDecisionApproveBody(BaseModel):
    decision_id: str = Field(..., min_length=8)
    vault_path: str = Field(..., min_length=4)
    chat_id: str = ""
    tenant_id: str = "default"
    user_id: str = ""


class CodeDecisionRejectBody(BaseModel):
    decision_id: str = Field(..., min_length=8)
    vault_path: str = Field(..., min_length=4)
    rationale: str = ""
    tenant_id: str = "default"
    user_id: str = ""


class UncertaintyResolveBody(BaseModel):
    event_id: str = Field(..., min_length=8)
    vault_path: str = Field(..., min_length=4)


@router.get("/loop/status", dependencies=[Depends(require_admin_key)])
def admin_loop_status(
    tenant_id: str = Query("default"),
    worker_id: str = Query(""),
) -> dict[str, Any]:
    """Último run loop, distance_vector y estado del circuit breaker."""
    import json

    from harness_core.skills.emit_correction_delta import circuit_breaker_redis_key, is_circuit_breaker_active

    tid = (tenant_id or "default").strip() or "default"
    wid = (worker_id or "").strip()
    last_run: dict[str, Any] | None = None
    try:
        from core.admin_identity import open_gateway_db

        with open_gateway_db(read_only=True) as db:
            esc = tid.replace("'", "''")
            raw = db.query(
                "SELECT run_id, distance_vector, actions_json, status, created_at "
                "FROM harness_core.loop_runs "
                f"WHERE tenant_id = '{esc}' "
                "ORDER BY created_at DESC LIMIT 1"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not rows:
                raw = db.query(
                    "SELECT run_id, distance_vector, actions_json, status, created_at "
                    "FROM harness_core.meditate_runs "
                    f"WHERE tenant_id = '{esc}' "
                    "ORDER BY created_at DESC LIMIT 1"
                )
                rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if rows and isinstance(rows[0], dict):
                last_run = rows[0]
    except Exception as exc:
        last_run = {"error": str(exc)}

    cb_active = is_circuit_breaker_active(tid, wid) if wid else False
    return {
        "tenant_id": tid,
        "worker_id": wid or None,
        "circuit_breaker_active": cb_active,
        "circuit_breaker_key": circuit_breaker_redis_key(tid, wid) if wid else None,
        "last_run": last_run,
    }


@router.post("/loop/tick", dependencies=[Depends(require_admin_key)])
def admin_loop_tick(body: AdminLoopTickBody) -> dict[str, Any]:
    """Disparo manual del grafo loop (admin)."""
    from harness_core.graphs.loop_graph import invoke_loop_run
    from harness_core.states.loop_state import HomeostasisTarget
    from harness_core.targets import load_homeostasis_targets

    tid = (body.tenant_id or "default").strip() or "default"
    wid = (body.worker_id or "").strip()
    if not wid:
        raise problem(400, "worker_id requerido", "Indica worker_id en el body.")

    vault = (body.vault_db_path or "").strip()
    if not vault:
        try:
            from duckclaw.gateway_db import get_gateway_db_path

            vault = get_gateway_db_path()
        except Exception as exc:
            raise problem(400, "vault_db_path", str(exc)) from exc

    targets_obj = HomeostasisTarget()
    try:
        from duckclaw import DuckClaw

        with DuckClaw(vault, read_only=True) as db:
            targets_obj = load_homeostasis_targets(db, tid)
    except Exception:
        pass

    from duckclaw.commands.loop import _resolve_loop_vault_user_id

    loop_user_id = _resolve_loop_vault_user_id(
        type("_VaultDb", (), {"_path": vault})(),
        chat_id=str(body.chat_id),
        tenant_id=tid,
        vault_user_id="admin",
    )
    result = invoke_loop_run(
        {
            "tenant_id": tid,
            "worker_id": wid,
            "chat_id": str(body.chat_id),
            "admin_chat_id": str(body.chat_id),
            "vault_db_path": vault,
            "user_id": loop_user_id,
            "delta_interval_seconds": int(body.delta_interval_seconds),
            "targets": targets_obj.model_dump(),
        },
    )
    return {"ok": True, "result": result}


@router.get("/meditate/status", dependencies=[Depends(require_admin_key)], include_in_schema=False)
def admin_meditate_status_alias(
    tenant_id: str = Query("default"),
    worker_id: str = Query(""),
) -> dict[str, Any]:
    return admin_loop_status(tenant_id=tenant_id, worker_id=worker_id)


@router.post("/meditate/tick", dependencies=[Depends(require_admin_key)], include_in_schema=False)
def admin_meditate_tick_alias(body: AdminLoopTickBody) -> dict[str, Any]:
    return admin_loop_tick(body)


@router.post("/code/approve", dependencies=[Depends(require_admin_key)])
def admin_code_decision_approve(
    body: CodeDecisionApproveBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Aprueba code_decision PENDING_HITL y crea PR en GitHub (backend soberano)."""
    try:
        con, resolved, _scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        tid = (body.tenant_id or "default").strip() or "default"
        uid = (body.user_id or actor or tid).strip() or tid

        from duckclaw import DuckClaw
        from duckclaw.hitl.code_decision_service import approve_code_decision

        duck = DuckClaw(resolved, read_only=True)
        try:
            result = approve_code_decision(
                duck,
                decision_id=body.decision_id.strip(),
                tenant_id=tid,
                user_id=uid,
                chat_id=(body.chat_id or "").strip(),
            )
        finally:
            duck.close()
        if result.get("error"):
            raise problem(400, "Aprobación fallida", str(result["error"]))
        return result
    finally:
        con.close()


@router.post("/code/reject", dependencies=[Depends(require_admin_key)])
def admin_code_decision_reject(
    body: CodeDecisionRejectBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Rechaza code_decision."""
    try:
        con, resolved, _scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        tid = (body.tenant_id or "default").strip() or "default"
        uid = (body.user_id or actor or tid).strip() or tid

        from duckclaw import DuckClaw
        from duckclaw.hitl.code_decision_service import reject_code_decision

        duck = DuckClaw(resolved, read_only=True)
        try:
            result = reject_code_decision(
                duck,
                decision_id=body.decision_id.strip(),
                tenant_id=tid,
                user_id=uid,
                rationale=body.rationale,
            )
        finally:
            duck.close()
        if result.get("error"):
            raise problem(400, "Rechazo fallido", str(result["error"]))
        return result
    finally:
        con.close()


@router.get("/code/decisions", dependencies=[Depends(require_admin_key)])
def admin_list_code_decisions(
    vault_path: str = Query(..., min_length=4),
    status: str = Query(default="PENDING_HITL"),
    limit: int = Query(default=20, ge=1, le=100),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Lista decisiones de código pendientes en el vault."""
    try:
        con, resolved, _scope = _duckdb_readonly_session(vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        st = (status or "").strip() or "PENDING_HITL"
        table_exists = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = 'code_decisions'
            """
        ).fetchone()[0]
        if not table_exists:
            return {"vault_path": resolved, "items": [], "status_filter": st}
        rows = con.execute(
            """
            SELECT id, repo, file_path, branch_name, decision_type, title, status, created_at, pr_url
            FROM main.code_decisions
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [st, int(limit)],
        ).fetchdf()
        return {"vault_path": resolved, "items": rows.to_dict(orient="records"), "status_filter": st}
    finally:
        con.close()


@router.get("/uncertainty/events", dependencies=[Depends(require_admin_key)])
def admin_list_uncertainty_events(
    vault_path: str = Query(..., min_length=4),
    status: str = Query(default="PENDING_HITL"),
    limit: int = Query(default=20, ge=1, le=100),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Lista eventos de incertidumbre epistémica del vault."""
    try:
        con, resolved, _scope = _duckdb_readonly_session(vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        st = (status or "").strip() or "PENDING_HITL"
        table_exists = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = 'agent_uncertainty_log'
            """
        ).fetchone()[0]
        if not table_exists:
            return {"vault_path": resolved, "items": [], "status_filter": st}
        rows = con.execute(
            """
            SELECT id, session_uid, worker_id, trigger_context, confidence_score,
                   description, proposed_questions, status, created_at
            FROM main.agent_uncertainty_log
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [st, int(limit)],
        ).fetchdf()
        return {"vault_path": resolved, "items": rows.to_dict(orient="records"), "status_filter": st}
    finally:
        con.close()


@router.post("/uncertainty/resolve", dependencies=[Depends(require_admin_key)])
def admin_resolve_uncertainty_event(
    body: UncertaintyResolveBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Resuelve un evento PENDING_HITL (equivalente a /resolve_uncertainty)."""
    con = None
    try:
        con, resolved, scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        from duckclaw import DuckClaw
        from duckclaw.hitl.uncertainty_service import resolve_uncertainty_event

        duck = DuckClaw(resolved, read_only=True)
        try:
            result = resolve_uncertainty_event(
                duck,
                event_id=body.event_id.strip(),
                tenant_id=(scope or {}).get("tenant_id") or "default",
                user_id=actor,
            )
        finally:
            duck.close()
        if result.get("error"):
            raise problem(400, "No se pudo resolver", str(result["error"]))
        return {"vault_path": resolved, **result}
    except HTTPException:
        raise
    except Exception as exc:
        raise problem(500, "Error resolviendo incertidumbre", str(exc)) from exc
    finally:
        if con is not None:
            con.close()
