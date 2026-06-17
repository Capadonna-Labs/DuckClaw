"""DB-first admin routes (runtime settings)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import (
    actor_from_header as _actor_from_header,
    admin_audit as _admin_audit,
    require_admin_key as _require_admin_key,
)

router = APIRouter(tags=["admin-db-first"])


class RuntimeSettingPatchItem(BaseModel):
    domain: str = Field(..., min_length=1)
    key: str = Field(..., min_length=1)
    value: Any = ""
    scope: str = "actor"
    value_kind: str = "string"
    secret: bool = False


class RuntimeSettingsPatchBody(BaseModel):
    settings: list[RuntimeSettingPatchItem] = Field(default_factory=list)


def _runtime_setting_scope(item: RuntimeSettingPatchItem, *, actor: str, tenant_id: str) -> tuple[str, str]:
    scope = (item.scope or "actor").strip().lower()
    if scope == "global":
        return "global", ""
    if scope == "tenant":
        return tenant_id, ""
    if scope == "actor":
        return tenant_id, actor
    raise ValueError(f"scope inválido: {item.scope}")


@router.get("/settings/runtime", dependencies=[Depends(_require_admin_key)])
async def list_runtime_settings(
    domain: list[str] | None = Query(None),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_runtime_settings import list_runtime_settings_effective
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        settings = list_runtime_settings_effective(
            db,
            tenant_id=profile["tenant_id"],
            actor_email=profile["email"],
            domains=domain or None,
        )
    return {
        "tenant_id": profile["tenant_id"],
        "actor_email": profile["email"],
        "settings": settings,
    }


@router.patch("/settings/runtime", dependencies=[Depends(_require_admin_key)])
async def patch_runtime_settings(
    body: RuntimeSettingsPatchBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import UpsertRuntimeSettingCommand

    updated: list[str] = []
    task_ids: list[str] = []
    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
    for item in body.settings:
        tenant_id, scoped_actor = _runtime_setting_scope(
            item,
            actor=profile["email"],
            tenant_id=profile["tenant_id"],
        )
        value = item.value
        value_json = value if isinstance(value, (dict, list)) else None
        value_text = "" if value_json is not None else str(value or "")
        command = UpsertRuntimeSettingCommand(
            tenant_id=tenant_id,
            actor_email=scoped_actor,
            domain=item.domain,
            key=item.key,
            value=value_text,
            value_json=value_json,
            value_kind="json" if value_json is not None else item.value_kind,
            secret=item.secret,
            updated_by=profile["email"],
        )
        task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
        command_status = poll_task_status_sync(task_id, timeout_sec=0.5)
        if command_status and command_status.status == "failed":
            raise ValueError(command_status.detail or "runtime setting write failed")
        task_ids.append(task_id)
        domain_key = f"{item.domain.strip().lower()}.{item.key.strip().lower()}"
        updated.append(domain_key)
        _admin_audit(
            "runtime_setting.updated",
            domain_key,
            f"scope={item.scope}",
            actor=profile["email"],
            meta={"domain": item.domain, "setting": item.key, "scope": item.scope},
        )
    return {"ok": True, "updated": updated, "task_id": task_ids[-1] if task_ids else "", "task_ids": task_ids}
