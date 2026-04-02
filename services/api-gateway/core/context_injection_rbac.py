"""RBAC para /context --add: admin en authorized_users o war room."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.gateway_acl_db import ReadOnlyGatewayAclDb, get_gateway_acl_duckdb, get_war_room_acl_duckdb
from core.war_rooms import is_war_room_tenant, wr_lookup_member_clearance

def _owner_bypass(user_id: str) -> bool:
    owner = (os.getenv("DUCKCLAW_OWNER_ID") or os.getenv("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    return bool(owner and user_id and str(user_id).strip() == str(owner).strip())


def _is_admin_authorized_users(db: Any, tenant_id: str, user_id: str) -> bool:
    tid = str(tenant_id or "").replace("'", "''")[:256]
    uid = str(user_id or "").replace("'", "''")[:256]
    try:
        raw = db.query(
            f"SELECT role FROM main.authorized_users "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            role = str(rows[0].get("role") or "").strip().lower()
            return role == "admin"
    except Exception:
        return False
    return False


def user_may_context_inject(
    *,
    tenant_id: str,
    user_id: str,
    telegram_guard_acl_db_path: str | None = None,
) -> bool:
    """
    True si el usuario puede ejecutar /context --add.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return False
    if _owner_bypass(uid):
        return True
    tid = str(tenant_id or "default").strip() or "default"

    if is_war_room_tenant(tid):
        wr_db = get_war_room_acl_duckdb()
        return wr_lookup_member_clearance(wr_db, tid, uid).strip().lower() == "admin"

    forced = (telegram_guard_acl_db_path or "").strip()
    if forced:
        db: Any = ReadOnlyGatewayAclDb(str(Path(forced).expanduser().resolve()))
    else:
        db = get_gateway_acl_duckdb()[0]
    return _is_admin_authorized_users(db, tid, uid)
