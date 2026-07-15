"""Analyze Word templates → section schema (Jinja placeholders, optional headings)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

# Identifiers and dotted paths: {{ body }}, {{ evidencia2.1 }}
_JINJA_VAR_RE = re.compile(
    r"\{\{\s*([a-zA-Z_][\w]*(?:\.[a-zA-Z0-9_][\w]*)*)\s*\}\}"
)
_WT_TEXT_RE = re.compile(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>")
_OUTLINE_TITLE_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*[\.\)]\s*)?(?:[A-ZÁÉÍÓÚÑ][A-Za-záéíóúñÁÉÍÓÚÑ0-9\s\-–—]{2,})$"
)


def _read_docx_xml(path: Path) -> str:
    with zipfile.ZipFile(path, "r") as zf:
        raw = zf.read("word/document.xml")
    return raw.decode("utf-8", errors="replace")


def _xml_w_t_plaintext(xml: str) -> str:
    """Concatena textos de w:t para recuperar Jinja partido entre runs de Word."""
    return "".join(_WT_TEXT_RE.findall(xml))


def _sections_from_jinja(xml: str) -> list[dict[str, Any]]:
    plaintext = _xml_w_t_plaintext(xml)
    haystack = f"{plaintext}\n{xml}"
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for match in _JINJA_VAR_RE.finditer(haystack):
        var = match.group(1).strip()
        if not var or var in seen:
            continue
        seen.add(var)
        label = var.replace(".", " · ").replace("_", " ").strip()
        out.append(
            {
                "id": var,
                "label": label.title() if label.islower() else label,
                "required": False,
            }
        )
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


def analyze_docx_template(path: str | Path) -> dict[str, Any]:
    """
    Analiza una plantilla .docx genérica (cualquier nicho).

    Fail-loud: sin placeholders Jinja ni headings/outline detectables → ValueError
    con pista accionable. No inventa secciones ajenas al Word del usuario.
    """
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

    raise ValueError(
        "No se detectaron secciones en la plantilla. "
        "Añade huecos Jinja ({{ nombre_seccion }} o {{ grupo.campo }}) "
        "o títulos con estilo Heading 1/2 en Word, y vuelve a registrar."
    )
