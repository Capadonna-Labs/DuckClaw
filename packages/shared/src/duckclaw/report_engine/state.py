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


_KIND_TEXT = "text"
_KIND_IMAGE = "image"
_DEFAULT_IMAGE_WIDTH_IN = 5.5


def _normalize_kind(raw: Any) -> str:
    return _KIND_IMAGE if str(raw or "").strip().lower() == _KIND_IMAGE else _KIND_TEXT


def _entry_from_schema_item(raw: dict[str, Any], sid: str) -> dict[str, Any]:
    entry = {
        "status": _SECTION_EMPTY,
        "content": "",
        "label": str(raw.get("label") or sid),
        "required": bool(raw.get("required", False)),
        "kind": _normalize_kind(raw.get("kind")),
        "updated_at": "",
    }
    if entry["kind"] == _KIND_IMAGE:
        try:
            entry["width_in"] = float(raw.get("width_in") or _DEFAULT_IMAGE_WIDTH_IN)
        except (TypeError, ValueError):
            entry["width_in"] = _DEFAULT_IMAGE_WIDTH_IN
    return entry


def init_state_from_schema(section_schema: list[dict[str, Any]]) -> dict[str, Any]:
    sections: dict[str, Any] = {}
    for raw in section_schema:
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("id") or "").strip()
        if not sid:
            continue
        sections[sid] = _entry_from_schema_item(raw, sid)
    return {"sections": sections}


def merge_missing_schema_sections(
    state: dict[str, Any],
    section_schema: list[dict[str, Any]],
) -> dict[str, Any]:
    """Añade huecos del schema que faltan en state (p. ej. imagen_4..15 tras ampliar blank).

    No pisa contenido ni status de secciones ya existentes.
    """
    sections = state.get("sections")
    if not isinstance(sections, dict):
        sections = {}
        state = {**state, "sections": sections}
    for raw in section_schema:
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("id") or "").strip()
        if not sid or sid in sections:
            continue
        sections[sid] = _entry_from_schema_item(raw, sid)
    state["sections"] = sections
    return state


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


def _path_key(part: str) -> str | int:
    """Jinja `{{ a.1 }}` resuelve el segmento como int, no como str '1'."""
    text = (part or "").strip()
    if text.isdigit():
        return int(text)
    return text


def _assign_nested(root: dict[str, Any], parts: list[str], value: Any) -> None:
    """Asigna value en árbol Jinja (ejecucion1.1 → {ejecucion1: {1: value}}).

    Importante: segmentos numéricos van como ``int``. En Jinja2,
    ``{{ ejecucion1.1 }}`` hace getitem con ``1`` (int); con clave ``'1'`` (str)
    el hueco queda vacío y el usuario ve la celda en blanco.
    """
    if not parts:
        return
    cursor: dict[str, Any] = root
    for part in parts[:-1]:
        key = _path_key(part)
        existing = cursor.get(key)
        if not isinstance(existing, dict):
            existing = {}
            cursor[key] = existing
        cursor = existing
    cursor[_path_key(parts[-1])] = value


from duckclaw.report_engine.docx_content import content_to_docxtpl_value


def build_render_context(state: dict[str, Any]) -> dict[str, Any]:
    """
    Contexto docxtpl/Jinja a partir del estado de secciones.

    - IDs planos → claves top-level string.
    - IDs dotted (a.b.c) → anidados para {{ a.b.c }} (segmentos numéricos = int).
    - Valores → RichText cuando hay saltos de línea o markdown inline (preserva celdas).
    """
    sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
    ctx: dict[str, Any] = {}
    for sid, entry in sections.items():
        if not isinstance(entry, dict):
            continue
        # Las secciones de imagen necesitan el objeto DocxTemplate (InlineImage);
        # se resuelven aparte en render.py, no aquí.
        if _normalize_kind(entry.get("kind")) == _KIND_IMAGE:
            continue
        content = str(entry.get("content") or "")
        value = content_to_docxtpl_value(content)
        key = str(sid)
        if "." in key:
            _assign_nested(ctx, key.split("."), value)
        else:
            ctx[key] = value
    return ctx


def image_render_specs(state: dict[str, Any]) -> list[dict[str, Any]]:
    """Secciones kind=image con path → [{key, path, width_in}] para InlineImage."""
    sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
    specs: list[dict[str, Any]] = []
    for sid, entry in sections.items():
        if not isinstance(entry, dict):
            continue
        if _normalize_kind(entry.get("kind")) != _KIND_IMAGE:
            continue
        path = str(entry.get("content") or "").strip()
        if not path:
            continue
        try:
            width_in = float(entry.get("width_in") or _DEFAULT_IMAGE_WIDTH_IN)
        except (TypeError, ValueError):
            width_in = _DEFAULT_IMAGE_WIDTH_IN
        specs.append({"key": str(sid), "path": path, "width_in": width_in})
    return specs


def assign_context_value(ctx: dict[str, Any], key: str, value: Any) -> None:
    """Asigna value respetando claves dotted anidadas (comparte lógica con el render)."""
    if "." in key:
        _assign_nested(ctx, key.split("."), value)
    else:
        ctx[key] = value
