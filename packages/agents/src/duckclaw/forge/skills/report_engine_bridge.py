"""Report Engine tool bridges — templates, instances, sections (transversal)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.forge.skills.search_project_knowledge_bridge import _open_hub_db


def _hub_db_path() -> str:
    from duckclaw.gateway_db import get_gateway_db_path, get_session_db_path

    for resolver in (get_session_db_path, get_gateway_db_path):
        path = (resolver() or "").strip()
        if path:
            return path
    raise RuntimeError("No hay ruta DuckDB del gateway para Report Engine.")


def _session_scope() -> tuple[str, str, str]:
    from duckclaw.forge.skills.knowledge_tool_context import (
        get_knowledge_tool_project_id,
        get_knowledge_tool_tenant_id,
        get_session_actor_email,
    )

    return (
        get_knowledge_tool_tenant_id(),
        get_session_actor_email(),
        get_knowledge_tool_project_id(),
    )


def _dispatch_write(payload: dict[str, Any]) -> None:
    from duckclaw.db_write_queue import enqueue_or_apply_duckdb_write_sync

    tenant_id, actor_email, _ = _session_scope()
    body = {
        "task_id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "actor_email": actor_email,
        **payload,
    }
    enqueue_or_apply_duckdb_write_sync(
        db_path=_hub_db_path(),
        command=body,
        user_id=actor_email,
        tenant_id=tenant_id,
    )


def list_report_templates(limit: int = 50) -> str:
    """Lista plantillas de informe visibles para el tenant y actor actual."""
    from duckclaw.report_engine.admin_report_read import list_report_templates as _list

    tenant_id, actor_email, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        rows = _list(db, tenant_id=tenant_id, actor_email=actor_email, limit=limit)
        return json.dumps({"templates": rows, "count": len(rows)}, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def register_report_template(
    template_docx_path: str,
    name: str,
    description: str = "",
    visibility: str = "private",
    template_id: str = "",
) -> str:
    """Analiza un .docx en el vault y registra una plantilla de informe (secciones Jinja o Heading)."""
    from duckclaw.forge.rag.knowledge_paths import resolve_readable_document_path
    from duckclaw.report_engine.analyzer import analyze_docx_template

    try:
        source = resolve_readable_document_path(relative_path=template_docx_path)
        analysis = analyze_docx_template(source)
        tid = (template_id or "").strip() or f"rtpl_{uuid.uuid4().hex[:10]}"
        _dispatch_write(
            {
                "command_type": "upsert_report_template",
                "template_id": tid,
                "name": (name or tid).strip(),
                "description": (description or "").strip(),
                "template_uri": str(source),
                "section_schema": analysis.get("sections") or [],
                "analyzer_mode": str(analysis.get("analyzer_mode") or "jinja"),
                "visibility": (visibility or "private").strip(),
            }
        )
        return json.dumps(
            {
                "template_id": tid,
                "name": name,
                "section_count": len(analysis.get("sections") or []),
                "sections": analysis.get("sections") or [],
                "analyzer_mode": analysis.get("analyzer_mode"),
                "warning": analysis.get("warning"),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def create_report_instance(
    template_id: str,
    title: str,
    period_key: str = "",
    project_id: str = "",
    instance_id: str = "",
) -> str:
    """Crea un informe en borrador desde una plantilla registrada."""
    try:
        tenant_id, actor_email, ctx_project = _session_scope()
        pid = (project_id or ctx_project or "").strip()
        iid = (instance_id or "").strip() or f"rpt_{uuid.uuid4().hex[:10]}"
        _dispatch_write(
            {
                "command_type": "create_report_instance",
                "instance_id": iid,
                "template_id": (template_id or "").strip(),
                "title": (title or "Informe").strip(),
                "period_key": (period_key or "").strip(),
                "project_id": pid,
            }
        )
        return json.dumps(
            {
                "instance_id": iid,
                "template_id": template_id,
                "title": title,
                "period_key": period_key,
                "project_id": pid,
                "status": "draft",
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def get_report_status(instance_id: str) -> str:
    """Devuelve progreso del informe: secciones completas, parciales y faltantes."""
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
        get_report_template,
    )
    from duckclaw.report_engine.state import summarize_status

    tenant_id, actor_email, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        instance = get_report_instance(db, instance_id=(instance_id or "").strip(), tenant_id=tenant_id)
        if not instance:
            return json.dumps({"error": "Instancia no encontrada"}, ensure_ascii=False)
        if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
            return json.dumps({"error": "Acceso denegado"}, ensure_ascii=False)
        template = get_report_template(db, template_id=str(instance["template_id"]), tenant_id=tenant_id)
        schema = (template or {}).get("section_schema") or []
        summary = summarize_status(instance["state"], schema)
        return json.dumps(
            {
                "instance_id": instance["instance_id"],
                "title": instance["title"],
                "period_key": instance["period_key"],
                "status": instance["status"],
                **summary,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def patch_report_section(
    instance_id: str,
    section_id: str,
    content: str,
    mode: str = "append",
    mark_complete: bool = False,
) -> str:
    """Añade o reemplaza contenido en una sección del informe en construcción."""
    try:
        _dispatch_write(
            {
                "command_type": "patch_report_section",
                "instance_id": (instance_id or "").strip(),
                "section_id": (section_id or "").strip(),
                "content": content or "",
                "mode": (mode or "append").strip().lower(),
                "mark_complete": bool(mark_complete),
            }
        )
        return json.dumps(
            {
                "instance_id": instance_id,
                "section_id": section_id,
                "mode": mode,
                "mark_complete": mark_complete,
                "status": "updated",
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def render_report_instance(instance_id: str) -> str:
    """Genera el DOCX del informe desde plantilla + estado actual."""
    from duckclaw.forge.rag.knowledge_paths import knowledge_output_roots
    from duckclaw.report_engine.admin_report_read import (
        actor_can_access_instance,
        get_report_instance,
        get_report_template,
    )
    from duckclaw.report_engine.render import render_instance_docx_from_uri

    tenant_id, actor_email, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        instance = get_report_instance(db, instance_id=(instance_id or "").strip(), tenant_id=tenant_id)
        if not instance:
            return json.dumps({"error": "Instancia no encontrada"}, ensure_ascii=False)
        if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
            return json.dumps({"error": "Acceso denegado"}, ensure_ascii=False)
        template = get_report_template(db, template_id=str(instance["template_id"]), tenant_id=tenant_id)
        if not template:
            return json.dumps({"error": "Plantilla no encontrada"}, ensure_ascii=False)

        roots = knowledge_output_roots()
        if not roots:
            return json.dumps({"error": "DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS no configurado"}, ensure_ascii=False)
        out_root = roots[0]

        rendered = render_instance_docx_from_uri(
            template_uri=str(template["template_uri"]),
            state_json=json.dumps(instance["state"], ensure_ascii=False),
            output_root=out_root,
            instance_id=str(instance["instance_id"]),
            title=str(instance["title"]),
            period_key=str(instance["period_key"]),
        )
        _dispatch_write(
            {
                "command_type": "update_report_instance_render",
                "instance_id": instance["instance_id"],
                "rendered_docx_uri": str(rendered["path"]),
                "status": "ready",
            }
        )
        return json.dumps(rendered, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    finally:
        if db is not None:
            try:
                db.close()
            except Exception:
                pass


def register_report_engine_tools(tools_list: list[Any]) -> None:
    tools_list.extend(
        [
            StructuredTool.from_function(
                list_report_templates,
                name="list_report_templates",
                description="Lista plantillas Word de informes registradas para este tenant.",
            ),
            StructuredTool.from_function(
                register_report_template,
                name="register_report_template",
                description=(
                    "Registra una plantilla .docx del vault. Detecta secciones por placeholders "
                    "{{ nombre }} o títulos Heading. Transversal: cualquier usuario define su plantilla."
                ),
            ),
            StructuredTool.from_function(
                create_report_instance,
                name="create_report_instance",
                description="Crea un borrador de informe desde plantilla (título, periodo, proyecto opcional).",
            ),
            StructuredTool.from_function(
                get_report_status,
                name="get_report_status",
                description=(
                    "Muestra qué secciones faltan, están parciales o completas. "
                    "Úsalo antes de proponer contenido o cerrar el informe."
                ),
            ),
            StructuredTool.from_function(
                patch_report_section,
                name="patch_report_section",
                description=(
                    "Actualiza una sección del informe (mode append|replace). "
                    "Ej.: agregar notas a obligaciones_1 del informe mensual."
                ),
            ),
            StructuredTool.from_function(
                render_report_instance,
                name="render_report_instance",
                description="Genera el Word final del informe en el vault de salida.",
            ),
        ]
    )
