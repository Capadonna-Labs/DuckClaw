"""Validación pre/post render — transversal, sin nicho."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

from duckclaw.report_engine.state import summarize_status

_JINJA_LEFTOVER_RE = re.compile(
    r"\{\{\s*([a-zA-Z_][\w]*(?:\.[a-zA-Z0-9_][\w]*)*)\s*\}\}"
)


def assert_template_is_patchable(analyzer_mode: str) -> None:
    """Plantillas solo por headings/outline no rellenan celdas con docxtpl."""
    mode = (analyzer_mode or "").strip().lower()
    if mode in ("", "jinja", "jinja_tables"):
        return
    raise ValueError(
        f"Plantilla analyzer_mode={mode!r} no es renderizable con docxtpl. "
        "Re-registra el .docx con placeholders Jinja en cada hueco "
        "({{ campo }} o {{ grupo.item }}) y vuelve a intentar."
    )


def assert_ready_to_render(
    state: dict[str, Any],
    section_schema: list[dict[str, Any]] | None,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Fail-loud si faltan secciones required (o cualquier missing si no force).

    force=true permite exportar borrador incompleto a propósito.
    """
    schema = section_schema if isinstance(section_schema, list) else []
    summary = summarize_status(state, schema)
    if force:
        return summary

    missing_items = summary.get("missing_sections") or []
    partial_items = summary.get("partial_sections") or []
    missing_ids: list[str] = []
    for item in missing_items:
        if isinstance(item, dict):
            missing_ids.append(str(item.get("id") or ""))
        else:
            missing_ids.append(str(item))

    required_ids = {
        str(s.get("id") or "").strip()
        for s in schema
        if isinstance(s, dict) and bool(s.get("required", False)) and str(s.get("id") or "").strip()
    }
    required_missing = [sid for sid in missing_ids if sid in required_ids]

    # Si no hay flags required en schema legacy, exigir cero missing.
    if required_ids:
        blockers = required_missing
        label = "secciones required vacías"
    else:
        blockers = missing_ids
        label = "secciones sin contenido"

    if blockers:
        raise ValueError(
            f"No se puede renderizar: {label}: {', '.join(blockers)}. "
            "Completa con patch_report_section o pasa force=true para exportar borrador."
        )

    if partial_items and required_ids:
        # Partials de required: permitir (tienen contenido) — status partial es OK
        pass

    return summary


def find_unresolved_placeholders(docx_path: str | Path) -> list[str]:
    """Lista {{ vars }} que quedaron literales en el .docx renderizado."""
    path = Path(docx_path)
    if not path.is_file():
        return []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    except Exception:
        return []
    # Concatena w:t por si Word partió el placeholder
    texts = re.findall(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>", xml)
    haystack = "".join(texts) + "\n" + xml
    seen: set[str] = set()
    out: list[str] = []
    for match in _JINJA_LEFTOVER_RE.finditer(haystack):
        var = match.group(1).strip()
        if var and var not in seen:
            seen.add(var)
            out.append(var)
    return out
