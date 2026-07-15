"""Tool bridge: escribir markdown/texto en raíces OUTPUT (Obsidian vault)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.document_toolbox.registry import assert_author_text_path
from duckclaw.forge.rag.knowledge_core import sha256_text
from duckclaw.forge.rag.knowledge_paths import (
    normalize_output_relative_path,
    resolve_knowledge_output_path,
)


def write_output_document(relative_path: str, content: str, output_root: str = "") -> str:
    """Escribe un documento markdown/texto bajo DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS."""
    text = (content or "").strip()
    if not text:
        return json.dumps({"error": "El contenido está vacío."}, ensure_ascii=False)

    try:
        rel = normalize_output_relative_path(relative_path)
        assert_author_text_path(rel)
        target = resolve_knowledge_output_path(relative_path=rel, output_root=output_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = text.encode("utf-8")
        target.write_bytes(data)
        payload: dict[str, Any] = {
            "relative_path": rel,
            "path": str(target),
            "byte_size": len(data),
            "checksum": sha256_text(text),
        }
        try:
            from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled, sync_file_after_write
            from duckclaw.forge.skills.knowledge_tool_context import (
                get_knowledge_tool_project_id,
                get_knowledge_tool_tenant_id,
            )

            if auto_sync_enabled():
                rag_sync = sync_file_after_write(
                    file_path=target,
                    tenant_id=get_knowledge_tool_tenant_id(),
                    project_id=get_knowledge_tool_project_id(),
                )
            else:
                rag_sync = {"synced": False, "reason": "auto_sync_disabled"}
            payload["rag_sync"] = rag_sync
        except Exception as exc:
            payload["rag_sync"] = {"synced": False, "reason": str(exc)}
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def register_write_output_document_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            write_output_document,
            name="write_output_document",
            description=(
                "Escribe un archivo de texto UTF-8 en DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS "
                "(.md, .txt, .json, .csv, .yaml, .py, .html, …). "
                "Prohibido .docx/.pdf/.xlsx y demás binarios: usa convert_document (pandoc) "
                "o render_docx_template / Report Engine. "
                "Informes corporativos: register_report_template → create_report_instance → "
                "patch_report_section → render_report_instance."
            ),
        )
    )
