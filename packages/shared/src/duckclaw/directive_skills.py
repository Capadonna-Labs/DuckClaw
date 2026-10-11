"""Directive skills ("/name" → its saved instruction text), shared by the admin chat
and scheduled prompts (heartbeat ``/crons --timestamp … --prompt``).

A directive skill lives in ``main.admin_skills`` (hub) with ``skill_type='directive'``;
invoking it prepends its ``description`` to the turn. Read-only lookup.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SLASH_NAME = re.compile(r"^/([a-zA-Z][a-zA-Z0-9_.-]{1,63})\b\s*(.*)$", re.DOTALL)
FRAMEWORK_TENANT = "framework"
_PACK = Path(__file__).resolve().parent / "seeds" / "framework_directive_skills_v1.json"


def seed_framework_directive_skills(db: Any) -> int:
    """Insert bundled directive skills whose name is not taken yet. Never overwrites an
    existing row (an edited or user-owned skill with the same name stays). DB-Writer only."""
    added = 0
    for skill in json.loads(_PACK.read_text(encoding="utf-8"))["skills"]:
        name = skill["name"]
        if _rows(db.execute("SELECT 1 FROM main.admin_skills WHERE lower(name) = lower(?)", [name])):
            continue
        db.execute(
            "INSERT INTO main.admin_skills (skill_id, name, description, skill_type, implementation_ref, "
            "owner_email, tenant_id, visibility, active) VALUES (?, ?, ?, 'directive', ?, 'system', ?, 'public', true)",
            [f"skl_fw_{name}", name, skill["description"][:4096], f"directive://{name}", FRAMEWORK_TENANT],
        )
        added += 1
    return added


def _rows(result: Any) -> list:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    return list(result) if isinstance(result, list) else []


def expand_directive_skill(
    db: Any, msg: str, *, tenant_id: str, actor_email: str | None = None
) -> tuple[str, str | None]:
    """``(msg_with_instruction, rest_without_prefix)`` when ``msg`` starts with an active
    directive skill of the tenant; else ``(msg, None)``. Never raises.

    ``actor_email=None`` (scheduled prompts, no interactive actor) matches any skill of
    the tenant — the tenant is the user's boundary; with an actor only public or owned ones.
    """
    t = (msg or "").strip()
    m = _SLASH_NAME.match(t) if t.startswith("/") else None
    if not m:
        return msg, None
    name, rest = m.group(1), m.group(2)
    # Framework defaults (tenant 'framework') apply to every tenant; the tenant's own skill wins.
    sql = (
        "SELECT description FROM main.admin_skills "
        "WHERE active = true AND skill_type = 'directive' AND tenant_id IN (?, ?) AND lower(name) = lower(?)"
    )
    params: list[Any] = [tenant_id, FRAMEWORK_TENANT, name]
    if actor_email is not None:
        sql += " AND (visibility = 'public' OR owner_email = ?)"
        params.append(actor_email)
    sql += " ORDER BY tenant_id = ?"
    params.append(FRAMEWORK_TENANT)
    try:
        rows = _rows(db.execute(sql, params))
    except Exception:
        return msg, None
    description = str(rows[0][0] or "").strip() if rows else ""
    if not description:
        return msg, None
    return f"[DIRECTIVA ACTIVA: /{name}]\n{description}\n\n{rest}".strip(), rest
