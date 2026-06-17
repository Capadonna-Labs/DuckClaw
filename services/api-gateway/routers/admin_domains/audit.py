from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, Query

from routers.admin_domains.admin_common import audit_log_path, require_admin_key as _require_admin_key_impl

router = APIRouter(prefix="/audit", tags=["admin-audit"])


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    _require_admin_key_impl(x_admin_key)


def _audit_log_path() -> Path:
    return audit_log_path()


def _load_audit_entries(limit: int) -> list[dict[str, Any]]:
    path = _audit_log_path()
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    entries.reverse()
    return entries


@router.get("", dependencies=[Depends(require_admin_key)])
async def get_admin_audit(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    return {"entries": _load_audit_entries(limit)}
