"""Directive skills ("/name" → its saved instruction text), shared by the admin chat
and scheduled prompts (heartbeat ``/crons --timestamp … --prompt``).

A directive skill lives in ``main.admin_skills`` (hub) with ``skill_type='directive'``;
invoking it prepends its ``description`` to the turn. Read-only lookup.
"""

from __future__ import annotations

import re
from typing import Any

_SLASH_NAME = re.compile(r"^/([a-zA-Z][a-zA-Z0-9_.-]{1,63})\b\s*(.*)$", re.DOTALL)


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
    sql = (
        "SELECT description FROM main.admin_skills "
        "WHERE active = true AND skill_type = 'directive' AND tenant_id = ? AND lower(name) = lower(?)"
    )
    params: list[Any] = [tenant_id, name]
    if actor_email is not None:
        sql += " AND (visibility = 'public' OR owner_email = ?)"
        params.append(actor_email)
    try:
        rows = _rows(db.execute(sql, params))
    except Exception:
        return msg, None
    description = str(rows[0][0] or "").strip() if rows else ""
    if not description:
        return msg, None
    return f"[DIRECTIVA ACTIVA: /{name}]\n{description}\n\n{rest}".strip(), rest
