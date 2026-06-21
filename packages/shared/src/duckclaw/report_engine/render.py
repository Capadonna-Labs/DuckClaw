"""Render report instance to DOCX (docxtpl + tenant template path)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from duckclaw.report_engine.state import build_render_context


def render_instance_docx_from_uri(
    *,
    template_uri: str,
    state_json: str,
    output_root: Path,
    instance_id: str,
    title: str = "",
    period_key: str = "",
) -> dict[str, Any]:
    template_path = Path(template_uri).expanduser().resolve()
    if not template_path.is_file():
        raise ValueError(f"Plantilla no accesible: {template_uri}")

    state = json.loads(state_json or "{}")
    if not isinstance(state, dict):
        raise ValueError("state_json inválido")

    context = build_render_context(state)
    context.setdefault("title", title)
    context.setdefault("subtitle", period_key)
    context.setdefault("period_key", period_key)
    context.setdefault("date", period_key)

    output_root.mkdir(parents=True, exist_ok=True)
    staging = output_root / ".report_templates"
    staging.mkdir(parents=True, exist_ok=True)
    staged = staging / f"{instance_id}_tpl.docx"
    shutil.copy2(template_path, staged)

    try:
        from docxtpl import DocxTemplate
    except ImportError as exc:
        raise ValueError("docxtpl no instalado (uv sync o duckops up)") from exc

    target = output_root / "reports" / f"{instance_id}.docx"
    target.parent.mkdir(parents=True, exist_ok=True)
    doc = DocxTemplate(str(staged))
    doc.render(context)
    doc.save(str(target))
    return {
        "path": str(target),
        "relative_path": f"reports/{instance_id}.docx",
        "byte_size": target.stat().st_size,
        "format": "docx",
    }
