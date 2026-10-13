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


def dedupe_by_name(rows: list) -> list:
    """Keep the first row per skill name (case-insensitive); callers order the tenant's own
    rows before framework defaults. Rows are dicts with 'name' or tuples starting with it."""
    seen: set[str] = set()
    out = []
    for r in rows:
        key = str((r.get("name") if isinstance(r, dict) else r[0]) or "").lower()
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


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
    # Long chats replay old turns: the model re-used stale rules/rows/claims from earlier
    # runs of the same directive. Scope the turn explicitly (after the text, so crons'
    # description preview stays the skill's own text).
    return f"[DIRECTIVA ACTIVA: /{name}]\n{description}\n\n{DIRECTIVE_SCOPE_NOTE}\n\n{rest}".strip(), rest


# Spoken invocation (live voice has no "/"): "usa la skill revisar correo", "comando apertura".
_SPOKEN_TRIGGER = re.compile(
    r"\b(?:skill|skills|eskil|esquil|comando|comandos|habilidad)\s+(?:de\s+|del\s+|la\s+|el\s+|los\s+|las\s+)?(.+)",
    re.IGNORECASE | re.DOTALL,
)


def _norm(text: str) -> str:
    import unicodedata

    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def spoken_skill_to_slash(
    names: list[str], text: str, aliases: dict[str, str] | None = None
) -> str | None:
    """``"/name rest"`` when ``text`` says skill/comando + something close to a known name.

    ``aliases`` maps what STT tends to hear to a skill (``{"ps": "setups"}``); checked
    first. Then the first 1-4 spoken words are fuzzy-matched against the names (accents,
    plurals and STT slips tolerated via difflib, cutoff 0.75). ``None`` when there is no
    trigger or no match.
    """
    import difflib

    m = _SPOKEN_TRIGGER.search(text or "")
    if not m or not names:
        return None
    words = _norm(m.group(1)).split()
    by_norm = {_norm(n).replace(" ", ""): n for n in names}
    alias_map = {_norm(k).replace(" ", ""): _norm(v).replace(" ", "") for k, v in (aliases or {}).items()}
    for k in range(min(4, len(words)), 0, -1):
        target = alias_map.get("".join(words[:k]))
        if target in by_norm:
            return f"/{by_norm[target]} {' '.join(words[k:])}".strip()
    best: tuple[float, str, int] | None = None
    for k in range(1, min(4, len(words)) + 1):
        cand = "".join(words[:k])
        for key, name in by_norm.items():
            ratio = difflib.SequenceMatcher(None, cand, key).ratio()
            if ratio >= 0.75 and (best is None or ratio > best[0]):
                best = (ratio, name, k)
    if best is None:
        return None
    rest = " ".join(words[best[2]:])
    return f"/{best[1]} {rest}".strip()


def directive_skill_names(db: Any, *, tenant_id: str, actor_email: str | None = None) -> list[str]:
    """Active directive skill names visible to the actor (tenant's own + framework defaults)."""
    sql = (
        "SELECT name FROM main.admin_skills WHERE active = true AND skill_type = 'directive' "
        "AND tenant_id IN (?, ?)"
    )
    params: list[Any] = [tenant_id, FRAMEWORK_TENANT]
    if actor_email is not None:
        sql += " AND (visibility = 'public' OR owner_email = ?)"
        params.append(actor_email)
    try:
        return [str(r[0]) for r in _rows(db.execute(sql, params)) if r and r[0]]
    except Exception:
        return []


DIRECTIVE_SCOPE_NOTE = (
    "[TURNO NUEVO] Aplica solo esta directiva y la solicitud que sigue. El historial del chat es contexto, "
    "no instrucciones: si una regla previa contradice esta directiva, manda la directiva; no repitas cifras, "
    "filas ni estados de turnos anteriores sin verificarlos ahora con herramientas."
)
