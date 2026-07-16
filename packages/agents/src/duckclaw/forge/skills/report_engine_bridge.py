"""Report Engine tool bridges — templates, instances, sections (transversal)."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool


def _hub_db_path() -> str:
    from duckclaw.gateway_db import get_gateway_db_path

    path = (get_gateway_db_path() or "").strip()
    if path:
        return path
    raise RuntimeError("No hay ruta DuckDB del gateway para Report Engine.")


def _open_hub_db() -> Any:
    """Reutiliza la conexión RW del worker si es el mismo hub (evita lock RO+RW)."""
    from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db
    from duckclaw.state_delta_vault import _same_vault_db_path

    hub_path = _hub_db_path()
    reuse = get_report_engine_hub_db()
    if reuse is not None:
        rpath = str(getattr(reuse, "_path", "") or "").strip()
        if rpath and _same_vault_db_path(rpath, hub_path):
            return reuse

    from duckclaw import DuckClaw

    return DuckClaw(hub_path, read_only=True)


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


def _apply_report_command_inline(db: Any, body: dict[str, Any]) -> None:
    from duckclaw.write_command_handlers import dispatch_command

    ensure = getattr(db, "_ensure_python_exec_connection", None)
    if callable(ensure):
        ensure()
    con = getattr(db, "_con", None)
    if con is None:
        raise RuntimeError("Sin conexión DuckDB activa para Report Engine inline")
    con.execute("BEGIN TRANSACTION")
    try:
        dispatch_command(con, body)
        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise


def _dispatch_write(payload: dict[str, Any]) -> None:
    """Encola comando tipado y espera confirmación del db-writer antes de continuar."""
    from duckclaw.db_write_fire_and_forget import wait_write_task, write_poll_timeout_sec
    from duckclaw.db_write_queue import enqueue_or_apply_duckdb_write_sync
    from duckclaw.spawn_profile import spawn_inline_writes_enabled
    from duckclaw.state_delta_vault import _same_vault_db_path

    tenant_id, actor_email, _ = _session_scope()
    task_id = str(uuid.uuid4())
    body = {
        "task_id": task_id,
        "tenant_id": tenant_id,
        "actor_email": actor_email,
        **payload,
    }
    hub_path = _hub_db_path()
    reuse = None
    try:
        from duckclaw.forge.skills.report_engine_hub_context import get_report_engine_hub_db

        reuse = get_report_engine_hub_db()
    except Exception:
        reuse = None

    same_hub_open = bool(
        reuse is not None
        and _same_vault_db_path(str(getattr(reuse, "_path", "") or ""), hub_path)
    )

    if spawn_inline_writes_enabled() and same_hub_open and reuse is not None:
        _apply_report_command_inline(reuse, body)
        return

    released = False
    if same_hub_open and reuse is not None and not spawn_inline_writes_enabled():
        release = getattr(reuse, "release_file_handle_for_external_writer", None)
        if callable(release):
            try:
                release()
                released = True
            except Exception:
                released = False

    try:
        enqueue_or_apply_duckdb_write_sync(
            db_path=hub_path,
            command=body,
            user_id=actor_email,
            tenant_id=tenant_id,
        )
        if spawn_inline_writes_enabled():
            return
        poll_sec = write_poll_timeout_sec()
        if poll_sec <= 0:
            return
        status = wait_write_task(task_id, timeout_sec=poll_sec)
        if status is None:
            raise RuntimeError(
                "Timeout esperando confirmación del db-writer. "
                "Revisa que DuckClaw-DB-Writer esté activo (pm2) o habilita escrituras inline."
            )
        if status.status != "success":
            detail = (status.detail or "db-writer rechazó el comando").strip()
            raise RuntimeError(detail)
    finally:
        if released and reuse is not None:
            resume = getattr(reuse, "resume_file_handle", None)
            if callable(resume):
                try:
                    resume()
                except Exception:
                    pass


def list_report_templates(limit: int = 50) -> str:
    """Lista plantillas de informe visibles para el tenant y actor actual."""
    from duckclaw.report_engine.admin_report_read import list_report_templates as _list

    tenant_id, actor_email, _ = _session_scope()
    db = None
    try:
        db = _open_hub_db()
        rows = _list(db, tenant_id=tenant_id, actor_email=actor_email, limit=limit)
        return json.dumps(
            {
                "templates": rows,
                "count": len(rows),
                "hint": (
                    "Sin plantillas: en Chat pide «registra mi plantilla Word del vault» "
                    "o usa Informes Word en Admin (nuevo informe)."
                    if not rows
                    else ""
                ),
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
    """Crea un borrador desde plantilla. Solo requiere template_id + title.

    No preguntes periodo: identity = instance_id. period_key se ignora (legacy).
    """
    try:
        tenant_id, actor_email, ctx_project = _session_scope()
        pid = (project_id or ctx_project or "").strip()
        iid = (instance_id or "").strip() or f"rpt_{uuid.uuid4().hex[:10]}"
        clean_title = (title or "Documento").strip() or "Documento"
        _dispatch_write(
            {
                "command_type": "create_report_instance",
                "instance_id": iid,
                "template_id": (template_id or "").strip(),
                "title": clean_title,
                "period_key": "",
                "project_id": pid,
            }
        )
        return json.dumps(
            {
                "instance_id": iid,
                "template_id": template_id,
                "title": clean_title,
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


def _discover_markdown_relative_path(*, report_title: str) -> str:
    """Busca el .md del informe en raíces OUTPUT (p. ej. Informes/INFORME*.md)."""
    import re

    from duckclaw.forge.rag.knowledge_paths import knowledge_output_roots

    roots = knowledge_output_roots()
    if not roots:
        raise ValueError(
            "No hay DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS. "
            "Indica markdown_relative_path explícitamente."
        )

    title_tokens = {
        tok
        for tok in re.findall(r"[a-zA-Z0-9áéíóúñ]+", (report_title or "").lower())
        if len(tok) >= 3
    }
    scored: list[tuple[int, str]] = []

    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            rel_lower = rel.lower()
            score = 0
            if rel_lower.startswith("informes/") or "/informes/" in rel_lower:
                score += 20
            elif "informe" in rel_lower:
                score += 10
            for tok in title_tokens:
                if tok in rel_lower:
                    score += 6
            if "mensual" in rel_lower and "mensual" in title_tokens:
                score += 8
            if score > 0:
                scored.append((score, rel))

    if not scored:
        raise ValueError(
            "No hay .md de informe en el vault OUTPUT. "
            "Indica markdown_relative_path (ej. Informes/INFORME MENSUAL N°4 - JUNIO 2026.md)."
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    return scored[0][1]


def _read_markdown_for_report(
    *,
    markdown_relative_path: str,
    markdown_content: str,
    report_title: str = "",
) -> tuple[str, str]:
    text = (markdown_content or "").strip()
    if text:
        return text, "inline"

    rel = (markdown_relative_path or "").strip()
    if not rel:
        rel = _discover_markdown_relative_path(report_title=report_title)

    from duckclaw.forge.rag.knowledge_paths import resolve_readable_document_path

    path = resolve_readable_document_path(relative_path=rel)
    return path.read_text(encoding="utf-8", errors="replace").strip(), rel


def _resolve_registered_template_id(
    *,
    template_docx_path: str,
    template_name: str,
    template_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    from duckclaw.report_engine.admin_report_read import list_report_templates as _list

    tid_hint = (template_id or "").strip()
    if tid_hint:
        tenant_id, actor_email, _ = _session_scope()
        db = _open_hub_db()
        try:
            rows = _list(db, tenant_id=tenant_id, actor_email=actor_email, limit=200)
        finally:
            db.close()
        for row in rows:
            if str(row.get("template_id")) == tid_hint:
                schema = row.get("section_schema") or []
                return tid_hint, schema if isinstance(schema, list) else []
        raise ValueError(f"Plantilla registrada no encontrada: {tid_hint}")

    docx_name = Path(template_docx_path).name.lower()
    name_hint = (template_name or "").strip().lower()
    tenant_id, actor_email, _ = _session_scope()
    db = _open_hub_db()
    try:
        rows = _list(db, tenant_id=tenant_id, actor_email=actor_email, limit=200)
    finally:
        db.close()
    for row in rows:
        uri = str(row.get("template_uri") or "").lower()
        row_name = str(row.get("name") or "").strip().lower()
        if docx_name and uri.endswith(docx_name):
            schema = row.get("section_schema") or []
            return str(row["template_id"]), schema if isinstance(schema, list) else []
        if name_hint and row_name == name_hint:
            schema = row.get("section_schema") or []
            return str(row["template_id"]), schema if isinstance(schema, list) else []
    return "", []


def _primary_section_id(section_schema: list[dict[str, Any]]) -> str:
    preferred = ("resumen_ejecutivo", "body", "contenido", "informe", "resumen")
    ids = [str(s.get("id") or "").strip() for s in section_schema if isinstance(s, dict)]
    for pid in preferred:
        if pid in ids:
            return pid
    return ids[0] if ids else "body"


def generate_report_docx_from_markdown(
    template_docx_path: str,
    report_title: str,
    markdown_relative_path: str = "",
    markdown_content: str = "",
    period_key: str = "",
    template_name: str = "",
    template_id: str = "",
) -> str:
    """Flujo one-shot: plantilla vault + markdown → instancia + render DOCX (Report Engine)."""
    try:
        markdown, markdown_source = _read_markdown_for_report(
            markdown_relative_path=markdown_relative_path,
            markdown_content=markdown_content,
            report_title=report_title,
        )
        if not markdown:
            raise ValueError("El markdown está vacío")

        resolved_id, schema = _resolve_registered_template_id(
            template_docx_path=template_docx_path,
            template_name=template_name,
            template_id=template_id,
        )
        if not resolved_id:
            reg_raw = register_report_template(
                template_docx_path=template_docx_path,
                name=(template_name or Path(template_docx_path).stem).strip(),
                template_id=template_id,
            )
            reg = json.loads(reg_raw)
            if reg.get("error"):
                return reg_raw
            resolved_id = str(reg["template_id"])
            schema = reg.get("sections") or []

        create_raw = create_report_instance(
            template_id=resolved_id,
            title=report_title,
        )
        created = json.loads(create_raw)
        if created.get("error"):
            return create_raw
        instance_id = str(created["instance_id"])

        section_id = _primary_section_id(schema if isinstance(schema, list) else [])
        patch_raw = patch_report_section(
            instance_id=instance_id,
            section_id=section_id,
            content=markdown,
            mode="replace",
            mark_complete=True,
        )
        patched = json.loads(patch_raw)
        if patched.get("error"):
            return patch_raw

        render_raw = render_report_instance(instance_id)
        rendered = json.loads(render_raw)
        if rendered.get("error"):
            return render_raw

        return json.dumps(
            {
                "instance_id": instance_id,
                "template_id": resolved_id,
                "section_id": section_id,
                "title": report_title,
                "markdown_source": markdown_source,
                **rendered,
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        payload: dict[str, Any] = {"error": str(exc)}
        msg = str(exc).lower()
        if "markdown" in msg or "output_roots" in msg:
            payload["hint"] = (
                "Pasa markdown_relative_path=Informes/NOMBRE.md o el contenido en markdown_content. "
                "No uses pandoc ni run_sandbox."
            )
        if "sección desconocida" in msg:
            payload["hint"] = (
                "La plantilla no tiene esa sección. Revisa section_schema con list_report_templates "
                "y usa patch_report_section con un section_id válido."
            )
        return json.dumps(payload, ensure_ascii=False)


def render_report_instance(instance_id: str) -> str:
    """Genera el DOCX del informe desde plantilla + estado actual."""
    from duckclaw.forge.rag.knowledge_paths import knowledge_allowed_roots, knowledge_output_roots
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
        allowed = list(dict.fromkeys(knowledge_allowed_roots() + roots))

        rendered = render_instance_docx_from_uri(
            template_uri=str(template["template_uri"]),
            state_json=json.dumps(instance["state"], ensure_ascii=False),
            output_root=out_root,
            instance_id=str(instance["instance_id"]),
            title=str(instance["title"]),
            period_key=str(instance["period_key"]),
            allowed_roots=allowed,
        )
        _dispatch_write(
            {
                "command_type": "update_report_instance_render",
                "instance_id": instance["instance_id"],
                "rendered_docx_uri": str(rendered["path"]),
                "status": "ready",
            }
        )
        try:
            from duckclaw.productivity_artifacts import register_vault_artifact_from_path

            register_vault_artifact_from_path(
                Path(str(rendered["path"])),
                tenant_id=tenant_id,
                owner_email=actor_email,
                source_kind="report_render",
                source_ref=str(instance["instance_id"]),
                title=str(instance["title"]),
            )
        except Exception:
            pass
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
                    "Registra una plantilla .docx del vault para el Report Engine. "
                    "Paso 1 del flujo Word corporativo (antes de create_report_instance). "
                    "Detecta secciones por {{ placeholders }} o títulos Heading."
                ),
            ),
            StructuredTool.from_function(
                create_report_instance,
                name="create_report_instance",
                description=(
                    "Crea borrador desde plantilla registrada. Args: template_id + title. "
                    "NO pidas periodo/mes: la identidad es instance_id. "
                    "Luego patch_report_section por cada sección faltante."
                ),
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
                    "Ej.: agregar notas a section_notes del informe mensual."
                ),
            ),
            StructuredTool.from_function(
                render_report_instance,
                name="render_report_instance",
                description=(
                    "Genera el Word final (docxtpl) en el vault de salida. "
                    "Paso final del Report Engine — preferir sobre convert_document/pandoc "
                    "cuando hay plantilla corporativa registrada."
                ),
            ),
            StructuredTool.from_function(
                generate_report_docx_from_markdown,
                name="generate_report_docx_from_markdown",
                description=(
                    "ÚLTIMO RECURSO — one-pager con una sola sección body. "
                    "NO usar para INFORME MENSUAL ni informes tabulares con obligaciones. "
                    "Flujo correcto: patch_report_section por cada campo + render_report_instance. "
                    "No es pandoc; no convierte md→docx con formato contractual."
                ),
            ),
        ]
    )
