from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from core.admin_identity import effective_actor_email, open_gateway_db
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import get_latest_worker_version, list_visible_workers_for_actor
from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.write_commands import DeactivateCatalogSkillCommand, UpsertCatalogSkillCommand

router = APIRouter(prefix="/catalog", tags=["admin-catalog-skills"])


class CatalogSkillCreateBody(BaseModel):
    name: str = Field(..., min_length=2, max_length=128)
    description: str = Field(default="", max_length=1024)
    skill_type: str = Field(default="python", max_length=64)
    implementation_ref: str = Field(..., min_length=3, max_length=512)
    visibility: str = Field(default="private", max_length=32)

    @field_validator("name")
    @classmethod
    def _valid_skill_name(cls, value: str) -> str:
        name = (value or "").strip()
        if not re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{1,127}", name):
            raise ValueError("name debe iniciar con letra y usar letras, números, _, . o -")
        return name

    @field_validator("visibility")
    @classmethod
    def _valid_visibility(cls, value: str) -> str:
        visibility = (value or "private").strip().lower()
        if visibility not in {"private", "public"}:
            raise ValueError("visibility debe ser private o public")
        return visibility


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


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else Path(__file__).resolve().parents[4]


def _audit_log_path() -> Path:
    path = _repo_root() / ".duckclaw" / "admin-audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _admin_audit(
    action: str,
    resource: str,
    detail: str,
    *,
    actor: str = "admin-ui",
    meta: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "resource": resource,
        "detail": detail,
        "meta": meta or {},
    }
    try:
        with _audit_log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _fetchall(result: Any) -> list[Any]:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    if isinstance(result, list):
        return result
    return []


def _actor_profile(actor: str) -> dict[str, Any]:
    actor_email = effective_actor_email(actor)
    if "@" not in actor_email:
        raise _problem(401, "Actor autenticado requerido", actor or "")
    with open_gateway_db(read_only=True) as db:
        return ensure_profile_for_user(db, email=actor_email)


def _skill_dto(name: str, implementation_ref: str) -> dict[str, str]:
    return {"id": name, "path": implementation_ref, "scope": "catalog"}


def _enqueue_catalog_skill_command(command: Any) -> str:
    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    command_status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if command_status and command_status.status == "failed":
        raise ValueError(command_status.detail or "catalog skill write failed")
    return task_id


@router.get("/skills", dependencies=[Depends(require_admin_key)])
async def catalog_skills(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    actor_email = effective_actor_email(actor)
    if "@" not in actor_email:
        return {"global": [], "template_local": []}

    global_skills: list[dict[str, str]] = []
    template_skills: list[dict[str, str]] = []
    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor_email)
        rows = _fetchall(
            db.execute(
                """
                SELECT name, implementation_ref
                FROM main.admin_skills
                WHERE active = true
                  AND tenant_id = ?
                  AND (owner_email = ? OR visibility = 'public')
                ORDER BY name
                """,
                [str(profile.get("tenant_id") or "default"), str(profile.get("email") or actor_email)],
            )
        )
        global_skills = [
            _skill_dto(str(name or ""), str(implementation_ref or ""))
            for name, implementation_ref in rows
            if str(name or "").strip()
        ]
        workers = list_visible_workers_for_actor(db, actor_email=actor_email)
        for worker in workers:
            worker_uid = str(worker.get("worker_uid") or "").strip()
            worker_id = str(worker.get("worker_id") or worker.get("id") or "").strip()
            if not worker_uid or worker_id == "default":
                continue
            latest = get_latest_worker_version(db, worker_uid=worker_uid) or {}
            files = latest.get("files_snapshot") if isinstance(latest, dict) else {}
            if not isinstance(files, dict):
                continue
            for rel in sorted(str(path).replace("\\", "/").lstrip("/") for path in files):
                if not rel.startswith("skills/") or not rel.endswith(".py"):
                    continue
                name = Path(rel).name
                if name.startswith("_"):
                    continue
                template_skills.append(
                    {
                        "id": Path(name).stem,
                        "worker_id": worker_id,
                        "path": f"db://admin_worker_catalog/{worker_uid}/{rel}",
                        "scope": "catalog",
                    }
                )
    return {"global": global_skills, "template_local": template_skills}


@router.post("/skills", dependencies=[Depends(require_admin_key)])
async def create_catalog_skill(
    body: CatalogSkillCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    command = UpsertCatalogSkillCommand(
        tenant_id=str(profile.get("tenant_id") or "default"),
        actor_email=str(profile.get("email") or effective_actor_email(actor)),
        name=body.name,
        description=body.description,
        skill_type=body.skill_type,
        implementation_ref=body.implementation_ref,
        visibility=body.visibility,
    )
    try:
        task_id = _enqueue_catalog_skill_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), body.name) from exc
    dto = _skill_dto(body.name, body.implementation_ref)
    _admin_audit("catalog.skill.upsert", dto["id"], dto["path"], actor=actor)
    return {"ok": True, "task_id": task_id, "skill": dto}


@router.delete("/skills/{name}", dependencies=[Depends(require_admin_key)])
async def deactivate_catalog_skill(
    name: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    command = DeactivateCatalogSkillCommand(
        tenant_id=str(profile.get("tenant_id") or "default"),
        actor_email=str(profile.get("email") or effective_actor_email(actor)),
        name=name,
    )
    try:
        task_id = _enqueue_catalog_skill_command(command)
    except ValueError as exc:
        raise _problem(400, str(exc), name) from exc
    _admin_audit("catalog.skill.deactivate", name, "", actor=actor)
    return {"ok": True, "task_id": task_id, "id": name}
