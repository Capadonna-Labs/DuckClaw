"""Section state machine for report instances."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

PatchMode = Literal["replace", "append"]

_SECTION_EMPTY = "empty"
_SECTION_PARTIAL = "partial"
_SECTION_COMPLETE = "complete"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_state_from_schema(section_schema: list[dict[str, Any]]) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for raw in section_schema:
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("id") or "").strip()
        if not sid:
            continue
        sections[sid] = {
            "status": _SECTION_EMPTY,
            "content": "",
            "label": str(raw.get("label") or sid),
            "required": bool(raw.get("required", False)),
            "updated_at": "",
        }
    return {"sections": sections}


def _status_for_content(content: str, *, mark_complete: bool) -> str:
    text = (content or "").strip()
    if not text:
        return _SECTION_EMPTY
    if mark_complete:
        return _SECTION_COMPLETE
    return _SECTION_PARTIAL


def patch_section(
    state: dict[str, Any],
    *,
    section_id: str,
    content: str,
    mode: PatchMode = "replace",
    mark_complete: bool = False,
) -> dict[str, Any]:
    sid = (section_id or "").strip()
    if not sid:
        raise ValueError("section_id vacío")
    sections = state.get("sections")
    if not isinstance(sections, dict):
        raise ValueError("state_json inválido: falta sections")
    entry = sections.get(sid)
    if not isinstance(entry, dict):
        raise ValueError(f"Sección desconocida: {sid}")

    incoming = (content or "").strip()
    if mode == "append" and entry.get("content"):
        merged = f"{str(entry['content']).rstrip()}\n\n{incoming}".strip()
    else:
        merged = incoming

    entry["content"] = merged
    entry["status"] = _status_for_content(merged, mark_complete=mark_complete)
    entry["updated_at"] = _utc_now()
    sections[sid] = entry
    state["sections"] = sections
    return state


def summarize_status(
    state: dict[str, Any],
    section_schema: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
    schema_ids = [
        str(s.get("id") or "").strip()
        for s in (section_schema or [])
        if isinstance(s, dict) and str(s.get("id") or "").strip()
    ]
    ids = schema_ids or list(sections.keys())
    missing: list[str] = []
    partial: list[str] = []
    complete: list[str] = []
    for sid in ids:
        entry = sections.get(sid) if isinstance(sections.get(sid), dict) else {}
        st = str(entry.get("status") or _SECTION_EMPTY)
        label = str(entry.get("label") or sid)
        item = {"id": sid, "label": label, "status": st}
        if st == _SECTION_COMPLETE:
            complete.append(sid)
        elif st == _SECTION_PARTIAL:
            partial.append(item)
        else:
            missing.append(item)

    total = len(ids) or 1
    pct = int(round((len(complete) / total) * 100))
    return {
        "section_count": len(ids),
        "complete_count": len(complete),
        "partial_count": len(partial),
        "missing_count": len(missing),
        "completion_percent": pct,
        "missing_sections": missing,
        "partial_sections": partial,
        "complete_sections": complete,
    }


def _assign_nested(root: dict[str, Any], parts: list[str], value: str) -> None:
    """Asigna value en árbol Jinja (evidencia2.1 → {evidencia2: {1: value}})."""
    if not parts:
        return
    cursor: dict[str, Any] = root
    for part in parts[:-1]:
        existing = cursor.get(part)
        if not isinstance(existing, dict):
            existing = {}
            cursor[part] = existing
        cursor = existing
    cursor[parts[-1]] = value


def build_render_context(state: dict[str, Any]) -> dict[str, Any]:
    """
    Contexto docxtpl/Jinja a partir del estado de secciones.

    - IDs planos → claves top-level string.
    - IDs dotted (a.b.c) → anidados para {{ a.b.c }}.
    """
    sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
    ctx: dict[str, Any] = {}
    for sid, entry in sections.items():
        if not isinstance(entry, dict):
            continue
        content = str(entry.get("content") or "")
        key = str(sid)
        if "." in key:
            _assign_nested(ctx, key.split("."), content)
        else:
            ctx[key] = content
    return ctx
