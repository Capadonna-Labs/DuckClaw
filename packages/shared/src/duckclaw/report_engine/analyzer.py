"""Analyze Word templates → section schema (Jinja placeholders, optional headings)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

_JINJA_VAR_RE = re.compile(r"\{\{\s*([a-zA-Z_][\w]*)\s*\}\}")
_OUTLINE_TITLE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[\.\)]\s*)?(?:[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ0-9\s\-–—]{2,})$"
)
_DEFAULT_MONTHLY_SECTIONS: list[dict[str, Any]] = [
    {"id": "resumen_ejecutivo", "label": "Resumen ejecutivo", "required": True},
    {"id": "kpis", "label": "KPIs", "required": False},
    {"id": "logros", "label": "Logros", "required": False},
    {"id": "riesgos", "label": "Riesgos", "required": False},
    {"id": "proximos_pasos", "label": "Próximos pasos", "required": False},
]


def _read_docx_xml(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        raw = zf.read("word/document.xml")
    return raw.decode("utf-8", errors="replace")


def _sections_from_jinja(xml: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for match in _JINJA_VAR_RE.finditer(xml):
        var = match.group(1).strip()
        if not var or var in seen:
            continue
        seen.add(var)
        out.append({"id": var, "label": var.replace("_", " ").title(), "required": False})
    return out


def _sections_from_headings(path: Path) -> list[dict[str, Any]]:
    try:
        from docx import Document
    except ImportError:
        return []
    doc = Document(str(path))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for para in doc.paragraphs:
        style = (para.style.name if para.style else "") or ""
        if not style.lower().startswith("heading"):
            continue
        label = (para.text or "").strip()
        if not label:
            continue
        sid = re.sub(r"[^a-zA-Z0-9_]+", "_", label.lower()).strip("_")[:64]
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append({"id": sid, "label": label, "required": False})
    return out


def _sections_from_outline_paragraphs(path: Path) -> list[dict[str, Any]]:
    try:
        from docx import Document
    except ImportError:
        return []
    doc = Document(str(path))
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for para in doc.paragraphs:
        label = (para.text or "").strip()
        if not label or len(label) > 120:
            continue
        style = ((para.style.name if para.style else "") or "").lower()
        is_heading = style.startswith("heading") or style.startswith("título")
        looks_title = bool(_OUTLINE_TITLE_RE.match(label)) and (
            label.isupper() or is_heading or len(label.split()) <= 10
        )
        if not looks_title:
            continue
        sid = re.sub(r"[^a-zA-Z0-9_]+", "_", label.lower()).strip("_")[:64]
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append({"id": sid, "label": label, "required": False})
    return out


def _docx_has_body_text(path: Path) -> bool:
    try:
        from docx import Document
    except ImportError:
        return path.stat().st_size > 0
    doc = Document(str(path))
    return any((p.text or "").strip() for p in doc.paragraphs)


def analyze_docx_template(path: str | Path) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError(f"Plantilla no encontrada: {target}")
    if target.suffix.lower() != ".docx":
        raise ValueError("Solo se analizan plantillas .docx")

    xml = _read_docx_xml(target)
    jinja_sections = _sections_from_jinja(xml)
    if jinja_sections:
        return {"analyzer_mode": "jinja", "sections": jinja_sections}

    heading_sections = _sections_from_headings(target)
    if heading_sections:
        return {"analyzer_mode": "headings", "sections": heading_sections}

    outline_sections = _sections_from_outline_paragraphs(target)
    if outline_sections:
        return {"analyzer_mode": "mixed", "sections": outline_sections}

    if _docx_has_body_text(target):
        return {
            "analyzer_mode": "mixed",
            "sections": list(_DEFAULT_MONTHLY_SECTIONS),
            "warning": (
                "Sin placeholders Jinja ni títulos detectables; se usan secciones estándar. "
                "Para rellenar el Word al renderizar, añade {{ resumen_ejecutivo }}, {{ kpis }}, etc. "
                "o usa la plantilla corporate_report del repo."
            ),
        }

    raise ValueError(
        "No se detectaron secciones. Usa placeholders Jinja {{ nombre_seccion }} "
        "o títulos con estilo Heading en Word."
    )
