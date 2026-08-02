"""Tool bridge: extract plain text from PDF/Office/HTML via MarkItDown."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.document_toolbox.extract import extract_document_text_from_path, markitdown_available
from duckclaw.forge.rag.knowledge_paths import resolve_readable_document_path
from duckclaw.forge.skills.knowledge_tool_copy import EXTRACT_DOCUMENT_TEXT_DESCRIPTION


def extract_document_text(relative_path: str, root_hint: str = "") -> str:
    """Extrae texto plano de PDF/Word/PPT/HTML bajo raíces permitidas (MarkItDown)."""
    try:
        source = resolve_readable_document_path(relative_path=relative_path, root_hint=root_hint)
        text, mime = extract_document_text_from_path(source)
        return json.dumps(
            {
                "relative_path": relative_path,
                "path": str(source),
                "char_count": len(text),
                "mime_hint": mime,
                "text": text[:120_000],
                "truncated": len(text) > 120_000,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        hint = None
        if not markitdown_available():
            hint = "Instala dependencias: uv sync o duckops up"
        payload: dict[str, Any] = {"error": str(exc)}
        if hint:
            payload["hint"] = hint
        return json.dumps(payload, ensure_ascii=False)


def register_extract_document_text_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            extract_document_text,
            name="extract_document_text",
            description=EXTRACT_DOCUMENT_TEXT_DESCRIPTION,
        )
    )
