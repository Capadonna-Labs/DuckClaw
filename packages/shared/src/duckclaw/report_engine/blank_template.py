"""Plantilla en blanco (texto + imágenes) para documentos desde cero.

No se versiona un .docx binario: se genera on-demand con python-docx bajo una
raíz permitida (OUTPUT). El schema marca las secciones de imagen con kind=image
para que el render las inserte como InlineImage (no como texto).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

BLANK_TEMPLATE_STEM = "blank_document"

# Bloques intercalados texto/imagen. Ninguno required: con ChainableUndefined los
# huecos no usados quedan vacíos y el render no falla.
BLANK_SECTION_SCHEMA: list[dict[str, Any]] = [
    {"id": "titulo", "label": "Título", "kind": "text", "required": False},
    {"id": "intro", "label": "Introducción", "kind": "text", "required": False},
    {"id": "imagen_1", "label": "Imagen 1", "kind": "image", "required": False, "width_in": 5.5},
    {"id": "texto_1", "label": "Texto 1", "kind": "text", "required": False},
    {"id": "imagen_2", "label": "Imagen 2", "kind": "image", "required": False, "width_in": 5.5},
    {"id": "texto_2", "label": "Texto 2", "kind": "text", "required": False},
    {"id": "imagen_3", "label": "Imagen 3", "kind": "image", "required": False, "width_in": 5.5},
    {"id": "texto_3", "label": "Texto 3", "kind": "text", "required": False},
    {"id": "cierre", "label": "Cierre", "kind": "text", "required": False},
]

_BODY_ORDER = [
    "intro",
    "imagen_1",
    "texto_1",
    "imagen_2",
    "texto_2",
    "imagen_3",
    "texto_3",
    "cierre",
]


def generate_blank_template_docx(target: Path) -> Path:
    """Genera el .docx en blanco con placeholders {{ id }} para docxtpl."""
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - entorno sin python-docx
        raise ValueError("python-docx no instalado (uv sync o duckops up)") from exc

    target.parent.mkdir(parents=True, exist_ok=True)
    doc = Document()
    doc.add_heading("{{ titulo }}", level=0)
    for section_id in _BODY_ORDER:
        doc.add_paragraph("{{ %s }}" % section_id)
    doc.save(str(target))
    return target


def ensure_blank_template_seed(output_root: Path) -> Path:
    """Devuelve la ruta del .docx en blanco bajo OUTPUT, generándolo si falta."""
    target = output_root / "templates" / f"{BLANK_TEMPLATE_STEM}.docx"
    if target.is_file() and target.stat().st_size > 0:
        return target
    return generate_blank_template_docx(target)
