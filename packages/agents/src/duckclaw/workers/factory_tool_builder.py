"""Worker tool list assembly: skills, SQL tools, schema inspection."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from duckclaw.db_write_queue import enqueue_typed_command
from duckclaw.write_commands import RawSqlCommand
from duckclaw.utils.logger import log_tool_execution_sync
from duckclaw.workers import read_pool
from duckclaw.workers.db_runtime import infer_user_id_for_writer as _infer_user_id_for_writer
from duckclaw.workers.loader import load_skills
from duckclaw.workers.manifest import WorkerSpec
from duckclaw.workers.tool_surface_policy import expose_privileged_mutation_tool_names

_log = logging.getLogger(__name__)


def _admin_sql_privileged_exposed(spec: WorkerSpec) -> bool:
    """True when manifest opts admin_sql into read_only workers via tool_surface."""

    return "admin_sql" in expose_privileged_mutation_tool_names(spec)


def _ensure_worker_duckdb_extensions(db: Any, spec: WorkerSpec) -> None:
    """INSTALL/LOAD extensiones declaradas en manifest (p. ej. httpfs + json para APIs remotas)."""
    exts = getattr(spec, "duckdb_extensions", None) or []
    if not exts:
        return
    for raw in exts:
        ext = str(raw).strip().lower()
        if not ext or not re.match(r"^[a-z][a-z0-9_]*$", ext):
            continue
        try:
            db.execute(f"INSTALL {ext};")
        except Exception:
            pass
        try:
            db.execute(f"LOAD {ext};")
        except Exception:
            pass


def _build_worker_tools(db: Any, spec: WorkerSpec, tenant_id: str = "default") -> list:
    """Build tool list: template skills + read/admin SQL (with allow-list)."""
    from langchain_core.tools import StructuredTool

    tools = load_skills(spec, db)
    schema = spec.schema_name

    # TimeContextSkill: si el manifest declara get_current_time o time_context, añadir la tool
    skills_list = getattr(spec, "skills_list", None) or []
    if "get_current_time" in skills_list or "time_context" in skills_list:
        try:
            from duckclaw.forge.skills.time_context import get_current_time
            tools.append(get_current_time)
        except Exception:
            pass

    def _enforce_allowed_tables(q_upper: str) -> Optional[json]:
        """Allow-list validation for queries touching DB tables."""
        if not spec.allowed_tables:
            return None
        # Permitir siempre information_schema (SHOW TABLES, esquema, etc.)
        if "INFORMATION_SCHEMA" in q_upper or "SHOW TABLES" in q_upper or "SHOW " in q_upper:
            return None
        for t in spec.allowed_tables:
            t_str = str(t)
            if t_str.upper() in q_upper or f"{schema}.{t_str}".upper() in q_upper:
                return None
        # No allowed table mentioned; check if query likely touches tables.
        if any(k in q_upper for k in ("FROM", "INTO", "UPDATE", "DELETE", "JOIN", "TABLE")):
            return json.dumps({"error": f"Solo se permiten las tablas: {', '.join(spec.allowed_tables)}."})
        return None

    def _qualify_allowed_tables(query: str, schema_name: str) -> str:
        """
        Prefix allowed table names with schema when unqualified.
        Example: FROM my_table -> FROM main.my_table
        """
        if not spec.allowed_tables:
            return query
        out = query
        for table in spec.allowed_tables:
            if "." in str(table):
                continue
            escaped = re.escape(table)
            # Replace only unqualified names (not already schema.table)
            out = re.sub(rf"(?<!\.)\b{escaped}\b", f"{schema_name}.{table}", out, flags=re.IGNORECASE)
        return out

    def _read_sql_worker(query: str) -> str:
        return read_pool.run_worker_read_sql(lambda qq: db.query(qq), spec, query)

    _read_sql_worker = log_tool_execution_sync(name="read_sql")(_read_sql_worker)

    tools.append(
        StructuredTool.from_function(
            _read_sql_worker,
            name="read_sql",
            description=(
                "Solo lectura SQL (SELECT/WITH/SHOW/DESCRIBE/EXPLAIN/PRAGMA) sobre DuckDB del worker. "
                "Úsala para consultar datos/tablas. "
                "NO la uses para generar o rellenar un informe Word / informe mensual: "
                "eso es Report Engine (register_report_template → patch_report_section → render)."
            ),
        )
    )

    def _admin_sql_worker(query: str) -> str:
        if not query or not query.strip():
            return json.dumps({"error": "Query vacío."})
        q = query.strip()
        upper = q.upper()

        allowed_tables_error = _enforce_allowed_tables(upper)
        if allowed_tables_error:
            return allowed_tables_error

        # Respetar read_only salvo admin_sql expuesto en tool_surface del manifest.
        if (
            spec.read_only
            and not _admin_sql_privileged_exposed(spec)
            and any(
            kw in upper
            for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE")
        )
        ):
            return json.dumps({"error": "Este trabajador es solo lectura. No se permiten escrituras."})

        try:
            # Para cualquier query de lectura, usar query()
            if upper.startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA")):
                return db.query(q)

            # Escrituras: cola singleton (workers RO) o ejecución en proceso (workers RW).
            db_path_str = str(getattr(db, "_path", "") or "").strip()
            if not db_path_str:
                return json.dumps({"error": "Sin ruta de base de datos para encolar escritura."})
            ro = bool(getattr(db, "_read_only", False))
            # Worker RW: este proceso ya mantiene ``duckdb.connect(..., read_only=False)`` al archivo.
            # Encolar un segundo RW en db-writer falla con lock en el mismo PID (gateway); ver logs db-writer.
            # Mutaciones RW en el handle actual del worker (sin encolar un segundo writer).
            if not ro and db_path_str != ":memory:":
                try:
                    db.execute(q)
                    return json.dumps({"status": "success"})
                except Exception as e:
                    return json.dumps({"error": str(e)})

            released_ro = False
            st = None
            try:
                # DuckDB: un handle RO en el gateway puede impedir que db-writer tome lock RW;
                # suspender antes de encolar.
                if ro and db_path_str != ":memory:":
                    susp = getattr(db, "suspend_readonly_file_handle", None)
                    resu = getattr(db, "resume_readonly_file_handle", None)
                    if callable(susp) and callable(resu):
                        susp()
                        released_ro = True
                resolved = str(Path(db_path_str).expanduser().resolve())
                uid = _infer_user_id_for_writer(resolved)
                cmd = RawSqlCommand(
                    query=q,
                    params=[],
                    tenant_id="default",
                )
                from duckclaw.db_write_fire_and_forget import wait_write_task, write_poll_timeout_sec
                from duckclaw.db_write_queue import enqueue_typed_command

                task_id = enqueue_typed_command(
                    cmd,
                    db_path=resolved,
                    user_id=uid,
                )
                poll_sec = write_poll_timeout_sec()
                st = wait_write_task(task_id, timeout_sec=poll_sec) if poll_sec > 0 else None
            except Exception as e:
                return json.dumps({"error": str(e)})
            finally:
                if released_ro:
                    try:
                        resu = getattr(db, "resume_readonly_file_handle", None)
                        if callable(resu):
                            resu()
                    except Exception:
                        pass
            if st is not None and st.status == "success":
                return json.dumps({"status": "success"})
            if st is not None and st.status == "failed":
                return json.dumps({"status": "failed", "detail": st.detail or "writer failed"})
            return json.dumps({"status": "enqueued_pending_confirmation"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    _admin_exposed = _admin_sql_privileged_exposed(spec)
    if not spec.read_only or _admin_exposed:
        tools.append(
            StructuredTool.from_function(
                _admin_sql_worker,
                name="admin_sql",
                description="SQL con permisos admin: lectura + escrituras (INSERT/UPDATE/DELETE/CREATE/ALTER/DROP si el worker no es read_only). Respeta allow-list de tablas del worker si aplica.",
            )
        )

    def _inspect_schema_worker() -> str:
        """Lista tablas de todos los esquemas disponibles para el worker."""
        return read_pool.run_inspect_schema_worker(lambda qq: db.query(qq))

    tools.append(
        StructuredTool.from_function(
            _inspect_schema_worker,
            name="inspect_schema",
            description=(
                "Lista tablas/esquema de la base DuckDB del worker. "
                "Úsala solo si preguntan qué tablas hay, estructura SQL o esquema. "
                "NO la uses si piden informe mensual, ejecuciones 1.1/2.1 o rellenar Word: "
                "esa intención es Report Engine, no inventario de tablas."
            ),
        )
    )

    from duckclaw.graphs.tools import get_db_path as _get_db_path_tool

    def _get_db_path_worker() -> str:
        return _get_db_path_tool(db)

    tools.append(
        StructuredTool.from_function(
            _get_db_path_worker,
            name="get_db_path",
            description="Devuelve la ruta o nombre del archivo .duckdb al que tiene acceso el agente. Usar cuando pregunten por el nombre de la base de datos.",
        )
    )

    from duckclaw.forge.skills.list_project_knowledge_bridge import register_list_project_knowledge_tool
    from duckclaw.forge.skills.read_project_knowledge_bridge import register_read_project_knowledge_tool
    from duckclaw.forge.skills.search_project_knowledge_bridge import register_search_project_knowledge_tool
    from duckclaw.forge.skills.extract_document_text_bridge import register_extract_document_text_tool
    from duckclaw.forge.skills.render_docx_template_bridge import register_render_docx_template_tool
    from duckclaw.forge.skills.write_output_document_bridge import register_write_output_document_tool
    from duckclaw.forge.skills.get_project_context_bridge import register_get_project_context_tool

    register_search_project_knowledge_tool(tools)
    register_list_project_knowledge_tool(tools)
    register_read_project_knowledge_tool(tools)
    # Enciclopedia Wikipedia offline (ZIM): baseline, no depende del skill research
    try:
        from duckclaw.forge.skills.kiwix_bridge import register_kiwix_tools

        register_kiwix_tools(tools, {"kiwix_enabled": True, "max_results": 8})
    except Exception:
        pass
    register_extract_document_text_tool(tools)
    register_write_output_document_tool(tools)
    register_render_docx_template_tool(tools)
    from duckclaw.forge.skills.export_docx_to_pdf_bridge import register_export_docx_to_pdf_tool

    register_export_docx_to_pdf_tool(tools)
    # Outbound serio = Report Engine (.docx); PDF = LibreOffice sobre ese Word (export_docx_to_pdf).
    # Inbound binario→texto = extract_document_text (MarkItDown). Ver docs/architecture/system_overview.md.
    register_get_project_context_tool(tools)
    from duckclaw.forge.skills.update_worker_system_prompt_bridge import register_update_system_prompt_tools

    register_update_system_prompt_tools(tools, db)
    from duckclaw.forge.skills.report_engine_bridge import register_report_engine_tools
    from duckclaw.prompt_policies.system_prompt import worker_has_report_engine_skill

    skills_list = [
        str(skill).strip().lower().replace("-", "_")
        for skill in (getattr(spec, "skills_list", None) or [])
    ]
    skill_configs = getattr(spec, "skill_configs", None) or {}
    if worker_has_report_engine_skill(spec):
        register_report_engine_tools(tools)
    from duckclaw.forge.skills.custom_reports_bridge import register_custom_reports_skill

    register_custom_reports_skill(tools, db, spec)
    if "github" in skills_list or "github" in skill_configs:
        from duckclaw.github.mcp_bridge import register_github_skill

        github_cfg = skill_configs.get("github")
        if github_cfg is None:
            github_cfg = {}
        register_github_skill(
            tools,
            github_cfg,
            logical_worker_id=str(
                getattr(spec, "logical_worker_id", None)
                or getattr(spec, "worker_id", None)
                or ""
            ),
            manifest_worker_slug=str(
                getattr(spec, "worker_slug", None)
                or getattr(spec, "worker_id", None)
                or ""
            ),
            db=db,
        )
    try:
        from duckclaw.forge.skills.mcp_connector_bridge import register_worker_mcp_connector_tools

        register_worker_mcp_connector_tools(
            tools,
            db=db,
            worker_id=str(
                getattr(spec, "worker_id", None)
                or getattr(spec, "logical_worker_id", None)
                or ""
            ),
            tenant_id=str(tenant_id or "default"),
        )
    except Exception:
        _log.warning("MCP connector tools registration skipped", exc_info=True)
    return tools
