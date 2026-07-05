from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/kanban", tags=["admin-kanban"])


class KanbanCreateBody(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    description: str = Field(default="", max_length=2000)
    status: str = "pendiente"
    worker_id: str | None = None
    tags: list[str] = Field(default_factory=list, max_length=16)
    priority: int = 0
    sort_order: int = 0


class KanbanUpdateBody(BaseModel):
    id: str = Field(..., min_length=1)
    title: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    status: str | None = None
    worker_id: str | None = None
    tags: list[str] | None = Field(default=None, max_length=16)
    priority: int | None = None
    sort_order: int | None = None


_KANBAN_UI_TO_DB_STATUS = {
    "pendiente": "todo",
    "en_progreso": "in_progress",
    "completo": "done",
    "todo": "todo",
    "in_progress": "in_progress",
    "done": "done",
    "cancelled": "cancelled",
}

_KANBAN_DB_TO_UI_STATUS = {
    "todo": "pendiente",
    "in_progress": "en_progreso",
    "done": "completo",
    "cancelled": "pendiente",
}


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _kanban_db_status(raw: str | None) -> str:
    status_value = str(raw or "pendiente").strip()
    mapped = _KANBAN_UI_TO_DB_STATUS.get(status_value)
    if not mapped:
        raise ValueError(f"status inválido: {status_value}")
    return mapped


def _kanban_ui_status(raw: str | None) -> str:
    return _KANBAN_DB_TO_UI_STATUS.get(str(raw or "todo").strip(), "pendiente")


def _kanban_tags(raw: Any) -> list[str]:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw or "[]")
        except json.JSONDecodeError:
            parsed = []
    else:
        parsed = raw
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        tag = str(item).strip()
        if tag and tag not in out:
            out.append(tag)
    return out[:16]


def _fetchone(result: Any) -> Any | None:
    if hasattr(result, "fetchone"):
        return result.fetchone()
    if isinstance(result, list):
        return result[0] if result else None
    return None


def _fetchall(result: Any) -> list[Any]:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    if isinstance(result, list):
        return result
    return []


def _kanban_card_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    card_id, title, description, status_value, worker_id, tags_json, created_at, updated_at = row
    return {
        "id": str(card_id),
        "title": str(title or ""),
        "description": str(description or ""),
        "status": _kanban_ui_status(str(status_value or "todo")),
        "worker_id": str(worker_id or "") or None,
        "tags": _kanban_tags(tags_json),
        "created_at": str(created_at),
        "updated_at": str(updated_at),
    }


def _kanban_existing_card(db: Any, *, card_id: str, tenant_id: str, actor_email: str) -> dict[str, Any] | None:
    row = _fetchone(
        db.execute(
            "SELECT card_id, title, description, status, assignee_email, tags_json, created_at, updated_at "
            "FROM main.admin_kanban_cards "
            "WHERE card_id = ? AND tenant_id = ? AND actor_email = ?",
            [card_id, tenant_id, actor_email],
        )
    )
    return _kanban_card_from_row(row) if row else None


def _enqueue_kanban_command(command: Any) -> str:
    from duckclaw.gateway_enqueue import enqueue_admin_command

    return enqueue_admin_command(command)


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_kanban_cards(
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        rows = _fetchall(
            db.execute(
                "SELECT card_id, title, description, status, assignee_email, tags_json, created_at, updated_at "
                "FROM main.admin_kanban_cards "
                "WHERE tenant_id = ? AND actor_email = ? AND status <> 'cancelled' "
                "ORDER BY sort_order ASC, updated_at DESC",
                [profile["tenant_id"], profile["email"]],
            )
        )
    return {"cards": [_kanban_card_from_row(row) for row in rows]}


@router.post("", dependencies=[Depends(require_admin_key)])
async def create_kanban_card(
    body: KanbanCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.write_commands import UpsertKanbanCardCommand

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)

    try:
        status_value = _kanban_db_status(body.status)
        command = UpsertKanbanCardCommand(
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            title=body.title.strip(),
            description=body.description.strip(),
            status=status_value,  # type: ignore[arg-type]
            priority=body.priority,
            sort_order=body.sort_order,
            worker_id=(body.worker_id or "").strip(),
            tags=body.tags,
        )
        task_id = _enqueue_kanban_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), "kanban") from exc

    card = {
        "id": command.card_id,
        "title": command.title,
        "description": command.description,
        "status": _kanban_ui_status(command.status),
        "worker_id": command.worker_id or None,
        "tags": command.tags,
        "created_at": "",
        "updated_at": "",
    }
    return {"ok": True, "task_id": task_id, "card": card}


@router.patch("", dependencies=[Depends(require_admin_key)])
async def update_kanban_card(
    body: KanbanUpdateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.write_commands import UpsertKanbanCardCommand

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        existing = _kanban_existing_card(
            db,
            card_id=body.id,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
        )
    if not existing:
        raise _problem(404, "Tarjeta no encontrada", body.id)

    try:
        status_value = _kanban_db_status(body.status or existing["status"])
        tags = body.tags if body.tags is not None else existing["tags"]
        command = UpsertKanbanCardCommand(
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            card_id=body.id,
            title=(body.title if body.title is not None else existing["title"]).strip(),
            description=(body.description if body.description is not None else existing["description"]).strip(),
            status=status_value,  # type: ignore[arg-type]
            priority=body.priority if body.priority is not None else 0,
            sort_order=body.sort_order if body.sort_order is not None else 0,
            worker_id=((body.worker_id if body.worker_id is not None else existing.get("worker_id")) or "").strip(),
            tags=tags,
        )
        task_id = _enqueue_kanban_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), body.id) from exc

    card = {
        "id": command.card_id,
        "title": command.title,
        "description": command.description,
        "status": _kanban_ui_status(command.status),
        "worker_id": command.worker_id or None,
        "tags": command.tags,
        "created_at": existing["created_at"],
        "updated_at": "",
    }
    return {"ok": True, "task_id": task_id, "card": card}


@router.delete("", dependencies=[Depends(require_admin_key)])
async def delete_kanban_card(
    id: str = Query(..., min_length=1),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.write_commands import DeleteKanbanCardCommand

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)

    try:
        command = DeleteKanbanCardCommand(
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            card_id=id,
        )
        task_id = _enqueue_kanban_command(command)
    except ValueError as exc:
        raise _problem(404, str(exc), id) from exc
    return {"ok": True, "task_id": task_id}
