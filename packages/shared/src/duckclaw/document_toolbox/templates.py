"""Corporate DOCX templates (docxtpl) — authoring lane."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from duckclaw.document_toolbox.pack import load_document_toolbox


def templates_seed_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "seeds" / "document_templates"


def template_path(template_id: str) -> Path:
    tid = (template_id or "").strip()
    if not tid:
        raise ValueError("template_id vacío")
    path = templates_seed_dir() / f"{tid}.docx"
    if not path.is_file():
        raise ValueError(f"Plantilla no encontrada: {tid}")
    return path


@lru_cache(maxsize=1)
def list_document_templates() -> list[dict[str, Any]]:
    pack = load_document_toolbox()
    templates = pack.get("templates")
    if not isinstance(templates, list):
        return []
    return [t for t in templates if isinstance(t, dict)]


def docxtpl_available() -> bool:
    try:
        import docxtpl  # noqa: F401

        return True
    except ImportError:
        return False


def render_docx_template(
    *,
    template_id: str,
    context: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    try:
        from docxtpl import DocxTemplate
    except ImportError as exc:
        raise ValueError(
            "docxtpl no instalado. Ejecuta: uv sync (o duckops up)"
        ) from exc

    src = template_path(template_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = DocxTemplate(str(src))
    doc.render(context or {})
    doc.save(str(output_path))
    return {
        "template_id": template_id,
        "path": str(output_path),
        "relative_path": output_path.name,
        "byte_size": output_path.stat().st_size,
        "format": "docx",
    }


def render_docx_template_json(
    *,
    template_id: str,
    context_json: str,
    output_path: Path,
) -> str:
    try:
        context = json.loads(context_json or "{}")
        if not isinstance(context, dict):
            raise ValueError("context debe ser un objeto JSON")
        payload = render_docx_template(
            template_id=template_id,
            context=context,
            output_path=output_path,
        )
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
