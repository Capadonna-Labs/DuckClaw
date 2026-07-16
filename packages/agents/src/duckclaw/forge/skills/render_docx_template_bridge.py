"""Tool bridge: render built-in DOCX templates (docxtpl) — subordinado a Report Engine."""

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


def _guard_builtin_docx(relative_path: str, *, allow_ad_hoc_docx: bool) -> None:
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
            blocked_tool="render_docx_template",
            relative_path=relative_path,
            output_format="docx",
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
            blocked_tool="render_docx_template",
            relative_path=relative_path,
            output_format="docx",
            db=None,
            allow_ad_hoc_docx=allow_ad_hoc_docx,
            fail_closed_without_db=True,
        )
    finally:
        _close_hub_db_if_owned(db)


def render_docx_template_tool(
    template_id: str,
    context_json: str,
    relative_path: str,
    output_root: str = "",
    allow_ad_hoc_docx: bool = False,
) -> str:
    """Rellena plantilla DOCX built-in (corporate_report) — no sustituye Report Engine."""
    try:
        rel = normalize_output_relative_path(relative_path, default_extension=".docx")
        _guard_builtin_docx(rel, allow_ad_hoc_docx=bool(allow_ad_hoc_docx))
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
        payload["hint_report_engine"] = (
            "Plantillas del vault: register_report_template → patch → render_report_instance"
        )
        return json.dumps(payload, ensure_ascii=False)


def register_render_docx_template_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            render_docx_template_tool,
            name="render_docx_template",
            description=(
                "SOLO plantilla built-in corporate_report (one-pager genérico). "
                "Si el actor tiene plantillas Report Engine, está bloqueado "
                "(usa render_report_instance). Escape: allow_ad_hoc_docx=true. "
                "Variables: title, subtitle, author, tenant_name, body, date."
            ),
        )
    )
