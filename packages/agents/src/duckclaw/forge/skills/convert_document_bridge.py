"""Tool bridge: convert text documents to DOCX/PDF/HTML via pandoc."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.document_toolbox.convert import convert_document_file, pandoc_available
from duckclaw.forge.rag.knowledge_paths import (
    normalize_output_relative_path,
    resolve_knowledge_output_path,
    resolve_readable_document_path,
)


def convert_document(
    relative_path: str,
    output_format: str = "docx",
    root_hint: str = "",
) -> str:
    """Convierte .md/.html/.txt del vault a DOCX, PDF u HTML (pandoc)."""
    fmt = (output_format or "docx").strip().lower()
    try:
        rel = normalize_output_relative_path(relative_path)
        source = resolve_readable_document_path(relative_path=rel, root_hint=root_hint)
        target = source.with_suffix(f".{fmt}")
        payload = convert_document_file(source=source, output_format=fmt, target=target)
        payload["relative_path"] = target.name
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        payload: dict[str, Any] = {"error": str(exc)}
        if not pandoc_available():
            payload["hint"] = "Instala pandoc en el host (brew install pandoc)"
        if fmt == "pdf":
            payload["docx_hint"] = "Prueba output_format=docx si falta motor PDF"
        return json.dumps(payload, ensure_ascii=False)


def export_output_document(
    relative_path: str,
    output_format: str = "docx",
    output_root: str = "",
) -> str:
    """Alias retrocompatible de convert_document."""
    return convert_document(relative_path, output_format=output_format, root_hint=output_root)


def register_convert_document_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            convert_document,
            name="convert_document",
            description=(
                "Convierte un documento de texto (.md, .html, .txt) del vault a DOCX, PDF u HTML "
                "usando pandoc. Para informes corporativos Word usa render_docx_template; "
                "para PDF desde DOCX generado, pasa la ruta .docx con output_format=pdf si pandoc lo admite."
            ),
        )
    )


def register_export_output_document_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            export_output_document,
            name="export_output_document",
            description="Alias de convert_document (legacy). Prefer convert_document.",
        )
    )
