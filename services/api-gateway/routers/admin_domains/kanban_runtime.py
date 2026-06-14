from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status

from routers.admin_domains.playground_chat import _playground_team_context

router = APIRouter(prefix="/kanban", tags=["admin-kanban-runtime"])


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    import main as gateway_main

    raw = (request_tenant or "").strip() or "default"
    return gateway_main._effective_tenant_id(raw)


def _kanban_status_from_audit(status: str, age_seconds: float) -> str:
    """Map latest task_audit_log row to kanban column id."""
    st = (status or "").strip().upper()
    if age_seconds < 30 * 60:
        return "en_progreso"
    if st == "SUCCESS":
        return "completo"
    return "pendiente"


def _resolve_kanban_worker_ids(
    workers: str | None,
    tenant_id: str | None,
) -> list[str]:
    raw_ids = [re.sub(r"[^a-zA-Z0-9_-]", "", w.strip()) for w in (workers or "").split(",")]
    worker_ids = [worker_id for worker_id in raw_ids if worker_id]
    if not worker_ids:
        team_ctx = _playground_team_context(tenant_id=tenant_id)
        worker_ids = list(team_ctx.get("workers") or [])
    return worker_ids


def _kanban_audit_states_by_worker(worker_ids: list[str]) -> dict[str, str]:
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    states: dict[str, str] = {worker_id: "pendiente" for worker_id in worker_ids}
    if not worker_ids:
        return states
    gateway_db_path = (get_gateway_db_path() or "").strip()
    if not gateway_db_path or not os.path.isfile(gateway_db_path):
        return states
    db = GatewayDbEphemeralReadonly(gateway_db_path)
    now = datetime.now(timezone.utc)
    worker_ids_sql = ", ".join("'" + worker_id.replace("'", "''") + "'" for worker_id in worker_ids)
    try:
        rows = db.query(
            f"""
            SELECT worker_id, status, created_at
            FROM task_audit_log
            WHERE worker_id IN ({worker_ids_sql})
            ORDER BY created_at DESC
            """
        )
    except Exception:
        return states
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        worker_id = str(row.get("worker_id") or "").strip()
        if not worker_id or worker_id in seen:
            continue
        seen.add(worker_id)
        created_at = row.get("created_at")
        age_seconds = 999999.0
        if created_at is not None:
            try:
                if hasattr(created_at, "tzinfo") and created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                age_seconds = max(0.0, (now - created_at).total_seconds())
            except Exception:
                age_seconds = 999999.0
        states[worker_id] = _kanban_status_from_audit(str(row.get("status") or ""), age_seconds)
    return states


def _kanban_latest_tasks_by_worker(worker_ids: list[str]) -> dict[str, dict[str, str]]:
    """Última fila de task_audit_log por worker (plan_title / query_prefix para Tablero)."""
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    tasks: dict[str, dict[str, str]] = {}
    if not worker_ids:
        return tasks
    gateway_db_path = (get_gateway_db_path() or "").strip()
    if not gateway_db_path or not os.path.isfile(gateway_db_path):
        return tasks
    db = GatewayDbEphemeralReadonly(gateway_db_path)
    worker_ids_sql = ", ".join("'" + worker_id.replace("'", "''") + "'" for worker_id in worker_ids)
    try:
        rows = db.query(
            f"""
            SELECT worker_id, query_prefix, plan_title
            FROM task_audit_log
            WHERE worker_id IN ({worker_ids_sql})
            ORDER BY created_at DESC
            """
        )
    except Exception:
        return tasks
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        worker_id = str(row.get("worker_id") or "").strip()
        if not worker_id or worker_id in seen:
            continue
        seen.add(worker_id)
        task: dict[str, str] = {}
        plan_title = str(row.get("plan_title") or "").strip()
        query_prefix = str(row.get("query_prefix") or "").strip()
        if plan_title:
            task["plan_title"] = plan_title
        if query_prefix:
            task["query_prefix"] = query_prefix
        if task:
            tasks[worker_id] = task
    return tasks


def _kanban_instance_key(worker_id: str, slot: int) -> str:
    return f"{worker_id}:{slot}"


@router.get("/worker-states", dependencies=[Depends(require_admin_key)])
async def kanban_worker_states(
    workers: str | None = Query(None, description="Comma-separated worker ids"),
    tenant_id: str | None = Query(None),
) -> dict[str, Any]:
    """
    Latest task_audit_log status per worker for Tablero sync (/workers team).
    Incluye claves compuestas ``{worker_id}:1`` (slot base) además de ``{worker_id}``.
    """
    worker_ids = _resolve_kanban_worker_ids(workers, tenant_id)
    if not worker_ids:
        return {"workers": [], "states": {}}
    audit = _kanban_audit_states_by_worker(worker_ids)
    states: dict[str, str] = dict(audit)
    for worker_id, state in audit.items():
        states[_kanban_instance_key(worker_id, 1)] = state
    return {"workers": worker_ids, "states": states}


@router.get("/swarm-slots", dependencies=[Depends(require_admin_key)])
async def kanban_swarm_slots(
    workers: str | None = Query(None, description="Comma-separated worker ids"),
    tenant_id: str | None = Query(None),
) -> dict[str, Any]:
    """
    Instancias swarm activas (Redis) y estados por ``{worker_id}:{slot}`` para el Tablero.
    """
    from duckclaw.graphs.subagent_run_id import list_active_swarm_slots

    worker_ids = _resolve_kanban_worker_ids(workers, tenant_id)
    if not worker_ids:
        return {"workers": [], "instances": [], "states": {}}

    tenant = _gateway_effective_tenant_id(tenant_id)
    raw_slots = list_active_swarm_slots(tenant, worker_ids)
    audit = _kanban_audit_states_by_worker(worker_ids)
    tasks = _kanban_latest_tasks_by_worker(worker_ids)

    active_by_worker: dict[str, set[int]] = {worker_id: set() for worker_id in worker_ids}
    instances: list[dict[str, Any]] = []
    for row in raw_slots:
        worker_id = str(row.get("worker_id") or "").strip()
        slot = int(row.get("slot") or 0)
        if not worker_id or slot < 1:
            continue
        active_by_worker.setdefault(worker_id, set()).add(slot)
        instances.append(
            {
                "worker_id": worker_id,
                "slot": slot,
                "chat_scope": row.get("chat_scope"),
                "started_at": row.get("started_at"),
                "active": True,
            }
        )

    states: dict[str, str] = {}
    for worker_id in worker_ids:
        base_slot_key = _kanban_instance_key(worker_id, 1)
        if 1 in active_by_worker.get(worker_id, set()):
            states[base_slot_key] = "en_progreso"
        else:
            states[base_slot_key] = audit.get(worker_id, "pendiente")
        for slot in sorted(active_by_worker.get(worker_id, set())):
            if slot >= 2:
                states[_kanban_instance_key(worker_id, slot)] = "en_progreso"

    return {"workers": worker_ids, "instances": instances, "states": states, "tasks": tasks}
