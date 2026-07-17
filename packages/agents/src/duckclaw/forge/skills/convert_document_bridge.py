"""Tool bridge: convert text documents to DOCX/PDF/HTML via pandoc."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.document_toolbox.convert import convert_document_file, pandoc_available
from duckclaw.forge.rag.knowledge_paths import (
    normalize_output_relative_path,
    project_convert_output_relative,
    resolve_knowledge_output_path,
    resolve_readable_document_path,
)


def _guard_docx_when_templates(
    relative_path: str,
    output_format: str,
    *,
    allow_ad_hoc_docx: bool,
) -> None:
    from duckclaw.forge.skills.knowledge_tool_context import (
        get_knowledge_tool_tenant_id,
        get_session_actor_email,
    )
    from duckclaw.forge.skills.report_engine_bridge import _close_hub_db_if_owned, _open_hub_db
    from duckclaw.report_engine.lane_guard import (
        assert_docx_uses_report_engine_when_templates_exist,
    )

    db = None
    try:
        db = _open_hub_db()
        assert_docx_uses_report_engine_when_templates_exist(
            blocked_tool="convert_document",
            relative_path=relative_path,
            output_format=output_format,
            db=db,
            tenant_id=get_knowledge_tool_tenant_id(),
            actor_email=get_session_actor_email(),
            allow_ad_hoc_docx=allow_ad_hoc_docx,
            fail_closed_without_db=True,
        )
    except ValueError:
        raise
    except Exception:
        assert_docx_uses_report_engine_when_templates_exist(
            blocked_tool="convert_document",
            relative_path=relative_path,
            output_format=output_format,
            db=None,
            allow_ad_hoc_docx=allow_ad_hoc_docx,
            fail_closed_without_db=True,
        )
    finally:
        _close_hub_db_if_owned(db)


def convert_document(
    relative_path: str,
    output_format: str = "docx",
    root_hint: str = "",
    output_root: str = "",
    allow_ad_hoc_docx: bool = False,
) -> str:
    """Convierte .md/.html/.txt legibles a DOCX/PDF/HTML bajo OUTPUT_ROOTS (pandoc)."""
    fmt = (output_format or "docx").strip().lower()
    try:
        rel = normalize_output_relative_path(relative_path, require_markdown=True)
        if fmt == "docx":
            _guard_docx_when_templates(
                rel, fmt, allow_ad_hoc_docx=bool(allow_ad_hoc_docx)
            )
        source = resolve_readable_document_path(relative_path=rel, root_hint=root_hint)
        out_rel = project_convert_output_relative(source=source, output_format=fmt)
        target = resolve_knowledge_output_path(relative_path=out_rel, output_root=output_root)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = convert_document_file(source=source, output_format=fmt, target=target)
        payload["relative_path"] = out_rel
        payload["path"] = str(target)
        try:
            from duckclaw.productivity_artifacts import register_vault_artifact_from_path

            indexed = register_vault_artifact_from_path(
                target,
                source_kind="convert_document",
                source_ref=out_rel,
                title=target.name,
            )
            if indexed:
                payload["productivity_artifact_id"] = indexed.get("artifact_id")
        except Exception as exc:
            payload["productivity_index"] = {"ok": False, "reason": str(exc)}
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
    allow_ad_hoc_docx: bool = False,
) -> str:
    """Alias retrocompatible de convert_document."""
    return convert_document(
        relative_path,
        output_format=output_format,
        root_hint=output_root,
        output_root=output_root,
        allow_ad_hoc_docx=allow_ad_hoc_docx,
    )


def register_convert_document_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            convert_document,
            name="convert_document",
            description=(
                "Convierte .md/.html/.txt a DOCX/PDF/HTML vía pandoc. "
                "Si el actor tiene plantillas Report Engine registradas, convert→docx "
                "está bloqueado (usa render_report_instance). Escape: allow_ad_hoc_docx=true "
                "solo para conversiones sin plantilla. Transversal a cualquier nicho."
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
