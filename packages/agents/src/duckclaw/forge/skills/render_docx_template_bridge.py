"""Tool bridge: render corporate DOCX templates (docxtpl)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.document_toolbox.templates import (
    docxtpl_available,
    list_document_templates,
    render_docx_template,
)
from duckclaw.forge.rag.knowledge_paths import normalize_output_relative_path, resolve_knowledge_output_path


def render_docx_template_tool(
    template_id: str,
    context_json: str,
    relative_path: str,
    output_root: str = "",
) -> str:
    """Rellena una plantilla DOCX corporativa y guarda el resultado en el vault de salida."""
    try:
        rel = normalize_output_relative_path(relative_path, default_extension=".docx")
        target = resolve_knowledge_output_path(relative_path=rel, output_root=output_root)
        context = json.loads(context_json or "{}")
        if not isinstance(context, dict):
            raise ValueError("context_json debe ser un objeto JSON")
        payload = render_docx_template(
            template_id=template_id,
            context=context,
            output_path=target,
        )
        payload["relative_path"] = rel
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        payload: dict[str, Any] = {"error": str(exc)}
        if not docxtpl_available():
            payload["hint"] = "uv sync o duckops up"
        known = [t.get("template_id") for t in list_document_templates()]
        if known:
            payload["available_templates"] = known
        return json.dumps(payload, ensure_ascii=False)


def register_render_docx_template_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            render_docx_template_tool,
            name="render_docx_template",
            description=(
                "Genera un Word corporativo desde plantilla (docxtpl). "
                "Plantilla built-in: corporate_report con variables "
                "title, subtitle, author, tenant_name, body, date (JSON en context_json). "
                "Guarda bajo OUTPUT vault; opcional convert_document a PDF después."
            ),
        )
    )
