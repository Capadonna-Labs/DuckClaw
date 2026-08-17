"""DB/tools/LLM initialization for worker LangGraph assembly."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Literal, Optional

from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.workers.context_monitor import (
    build_context_monitor_node as _build_context_monitor_node,
    build_summary_llm as _build_summary_llm,
)
from duckclaw.workers.db_runtime import (
    apply_forge_attaches as _apply_forge_attaches,
    get_db_path as _get_db_path,
    resolve_shared_db_path as _resolve_shared_db_path,
    same_duckdb_file as _same_duckdb_file,
)
from duckclaw.workers.factory_agent_node_helpers import (
    _TASK_AWARENESS_PROMPT,
    _identity_fields,
)
from duckclaw.workers.factory_graph_agent_bind import build_agent_llm_bind
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_tool_builder import _build_worker_tools
from duckclaw.workers.identity import load_worker_runtime_policy
from duckclaw.prompt_policies.system_prompt import resolve_effective_system_prompt_for_worker
from duckclaw.workers.loader import append_domain_closure_block
from duckclaw.workers.manifest import load_manifest
from duckclaw.workers.provider_input_budget import (
    configure_provider_budget_runtime_db_provider as _configure_provider_budget_runtime_db_provider,
    normalized_context_pruning as _normalized_context_pruning,
)
from duckclaw.workers.runtime_policy_helpers import (
    worker_has_runtime_capability as _worker_has_runtime_capability,
)
from duckclaw.workers.skill_tool_registry import (
    register_post_llm_skill_tools as _register_post_llm_skill_tools,
    register_pre_llm_skill_tools as _register_pre_llm_skill_tools,
)
from duckclaw.workers.tool_binding import (
    filter_tools_for_sandbox,
    groq_tools_without_reddit_for_bind as _groq_tools_without_reddit_for_bind,
    mlx_tools_for_bind as _mlx_tools_for_bind,
)

_log = logging.getLogger(__name__)


def initialize_worker_graph_context(
    worker_id: str,
    db_path: Optional[str],
    llm: Optional[Any],
    *,
    templates_root: Optional[Path] = None,
    instance_name: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    shared_db_path: Optional[str] = None,
    reuse_db: Any | None = None,
    tool_surface: Literal["full", "context_synthesis", "visual_generation", "url_research"] = "full",
    incoming_hint: str | None = None,
    open_vault_read_only: bool = False,
    db: Any | None = None,
    tenant_id: str = "default",
) -> WorkerGraphContext:
    ctx = WorkerGraphContext(
        worker_id=worker_id,
        tool_surface=tool_surface,
        tenant_id=tenant_id,
        instance_name=instance_name,
        llm=llm,
    )
    spec = load_manifest(worker_id, templates_root, db=db, tenant_id=tenant_id)
    ctx.spec = spec
    if db is not None:
        try:
            spec.runtime_policy = load_worker_runtime_policy(
                db,
                getattr(spec, "logical_worker_id", None) or worker_id,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            _log.debug("worker runtime policy unavailable for %s: %s", worker_id, exc)
    path = _get_db_path(worker_id, instance_name, db_path)
    ctx.path = path
    shared_resolved = _resolve_shared_db_path(spec, shared_db_path)
    ctx.shared_resolved = shared_resolved

    from duckclaw import DuckClaw

    reuse_path = ""
    if reuse_db is not None:
        reuse_path = str(getattr(reuse_db, "_path", "") or "").strip()
    reuse_read_only = bool(getattr(reuse_db, "_read_only", False)) if reuse_db is not None else False
    same_as_reuse = bool(reuse_db is not None and reuse_path and _same_duckdb_file(reuse_path, path))
    effective_vault_ro = bool(spec.read_only) or bool(open_vault_read_only)
    if same_as_reuse and not (shared_resolved or "").strip() and not open_vault_read_only:
        db = reuse_db
        _log.debug(
            "build_worker_graph: reuse DuckClaw (same file) path=%s ro=%s",
            path, reuse_read_only,
        )
    else:
        from typing import Literal as _Literal

        _engine: _Literal["auto", "python"] = (
            "python"
            if not effective_vault_ro and (path or "").strip() not in ("", ":memory:")
            else "auto"
        )
        db = DuckClaw(path, read_only=effective_vault_ro, engine=_engine)
    ctx.db = db
    # DuckDB no permite dos conexiones con config distinta al mismo archivo en el mismo PID.
    # Si ya tenemos una conexión (reuse_db) al mismo path, reusarla sin abrir otra.
    db_open_path = str(getattr(db, "_path", "") or path or "").strip()
    vault_path_for_attach = str(path or "").strip()
    same_as_attached = _same_duckdb_file(db_open_path, vault_path_for_attach)
    skip_private_attach = same_as_reuse or same_as_attached
    if same_as_attached:
        _log.debug(
            "build_worker_graph: vault path == db path, skip ATTACH. path=%s",
            path,
        )
    _apply_forge_attaches(
        db,
        path,
        shared_resolved,
        private_attach_read_only=effective_vault_ro,
        shared_attach_read_only=True,
        skip_private_attach=skip_private_attach,
    )
    prompt_policies = PromptPolicyResolver(db=db)

    system_prompt = resolve_effective_system_prompt_for_worker(
        db,
        spec,
        tenant_id=tenant_id,
    )
    try:
        _configure_provider_budget_runtime_db_provider(lambda: db)
    except Exception:
        pass
    tools = _build_worker_tools(db, spec, tenant_id=tenant_id)
    _register_pre_llm_skill_tools(
        tools,
        spec,
        tool_surface=tool_surface,
        incoming_hint=incoming_hint or "",
    )
    tools_by_name = {t.name: t for t in tools}

    # Inferencia Elástica (Hardware-Aware): si el manifest tiene inference y no se pasó provider/model/base_url explícito, detectar hardware
    inference_config = getattr(spec, "inference_config", None)
    if inference_config is not None and not llm_provider and not llm_model and not llm_base_url:
        try:
            from duckclaw.integrations.hardware_detector import (
                get_inference_config,
                resolve_llm_params_from_config,
            )
            config = get_inference_config(inference_config)
            provider, model, base_url = resolve_llm_params_from_config(config)
            provider = (provider or "none_llm").strip().lower()
            model = (model or "").strip()
            base_url = (base_url or "").strip()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Hardware detection failed or fallback disabled: %s", e)
            provider = "none_llm"
            model = ""
            base_url = ""
    else:
        provider = (llm_provider or os.environ.get("DUCKCLAW_LLM_PROVIDER") or "none_llm").strip().lower()
        model = (llm_model or os.environ.get("DUCKCLAW_LLM_MODEL") or "").strip()
        base_url = (llm_base_url or os.environ.get("DUCKCLAW_LLM_BASE_URL") or "").strip()

    if llm is None and provider != "none_llm":
        from duckclaw.integrations.llm_providers import build_llm

        # Tripleta del chat/worker gana sobre DUCKCLAW_LLM_* del entorno (p. ej. default mlx).
        llm = build_llm(
            provider,
            model,
            base_url,
            prefer_env_provider=False,
            db=db,
            tenant_id=tenant_id,
        )
    elif llm is None:
        llm = None

    if llm is not None:
        from duckclaw.integrations.llm_providers import reconcile_worker_provider_label

        provider = reconcile_worker_provider_label(llm, provider, llm_provider)

    llm_fallback: Any | None = None
    if llm is not None:
        try:
            from duckclaw.integrations.llm_providers import build_llm_fallback_from_env

            llm_fallback = build_llm_fallback_from_env()
        except Exception as _fb_exc:
            _log.debug("LLM fallback skipped: %s", _fb_exc)

    _cp_early = _normalized_context_pruning(spec, provider=provider)
    llm_summary: Any = None
    if llm is not None and _cp_early.get("enabled"):
        llm_summary = _build_summary_llm(llm, provider=provider, model=model, base_url=base_url)

    _register_post_llm_skill_tools(tools, spec, db=db, llm=llm, tenant_id=tenant_id)
    tools_by_name = {t.name: t for t in tools}

    from duckclaw.prompt_policies.system_prompt import append_android_mcp_directive_if_tools

    system_prompt = append_android_mcp_directive_if_tools(db, system_prompt, tools)

    try:
        from duckclaw.extensions.skills import invoke_extension_worker_skill_hooks

        _lid_skills = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip()
        invoke_extension_worker_skill_hooks(
            tools=tools,
            spec=spec,
            db=db,
            llm=llm,
            logical_worker_id=_lid_skills,
            worker_path=str(path or ""),
        )
        tools_by_name = {t.name: t for t in tools}
    except Exception:
        _log.debug("extension worker skill hooks skipped", exc_info=True)

    if getattr(spec, "homeostasis_config", None):
        try:
            from duckclaw.forge.skills.homeostasis_bridge import register_homeostasis_skill
            register_homeostasis_skill(tools, spec, db, tools_by_name)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass
    try:
        from duckclaw.forge.skills.homeostasis_bridge import register_goals_alignment_skill

        if "assess_crons_alignment" not in tools_by_name:
            register_goals_alignment_skill(tools, db)
            tools_by_name = {t.name: t for t in tools}
    except Exception:
        pass
    try:
        from duckclaw.forge.skills.loop_bridge import register_loop_skill

        register_loop_skill(tools, db)
    except Exception:
        pass

    # Strix Sandbox: `run_sandbox` con LLM (política zero-trust si falta YAML); browser opt-in en manifest.
    try:
        if llm is not None:
            from duckclaw.framework_tool_pack import ensure_baseline_worker_files

            ensure_baseline_worker_files(spec.worker_dir)
            from duckclaw.graphs.sandbox import (
                browser_sandbox_tool_factory,
                get_browser_session_url_tool_factory,
                sandbox_tool_factory,
            )

            if getattr(spec, "browser_sandbox", False) and "run_browser_sandbox" not in tools_by_name:
                tools.append(browser_sandbox_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
            if getattr(spec, "browser_sandbox", False) and "get_browser_session_url" not in tools_by_name:
                tools.append(get_browser_session_url_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
            if "run_sandbox" not in tools_by_name:
                tools.append(sandbox_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
    except Exception:
        pass

    # Aplicar LangSmith config al grafo final (no solo al llm) si está habilitado
    send_to_langsmith = os.environ.get("DUCKCLAW_SEND_TO_LANGSMITH", "false").lower() == "true"
    if send_to_langsmith:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        # Honor explicitly set project in env, otherwise fallback to spec name or default
        if not os.environ.get("LANGCHAIN_PROJECT"):
            os.environ["LANGCHAIN_PROJECT"] = instance_name or getattr(spec, "name", "DuckClaw") or "default"
        # Si la API KEY no existe en el entorno, LangSmith simplemente la ignorará o fallará silenciosamente
    else:
        # Desactivar explícitamente para esta instanciación si estaba globalmente activo
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    from langgraph.graph import END, StateGraph
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

    has_homeostasis = bool(getattr(spec, "homeostasis_config", None))
    _task_block = _TASK_AWARENESS_PROMPT.strip()
    _system_prompt_only = (system_prompt or "").strip()
    _task_block_resolved = _task_block
    effective_prompt = _system_prompt_only + "\n\n" + _task_block_resolved
    # Cierre de dominio = última instrucción al modelo (domain_closure.md del worker).
    effective_prompt = append_domain_closure_block(effective_prompt, spec)
    _lid = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip()
    _cp = _normalized_context_pruning(spec, provider=provider)
    use_cm = bool(_cp.get("enabled"))
    _schema_digest = ""
    if _cp.get("enabled"):
        schema_name = (str(getattr(spec, "schema_name", None) or "")).strip()
        allowed_tables = list(getattr(spec, "allowed_tables", None) or [])
        at = ", ".join(str(table) for table in allowed_tables) if allowed_tables else "(ninguna lista explícita)"
        _schema_digest = (
            f"\n\nContexto de datos:\nEsquema configurado: {schema_name or '(no especificado)'}; "
            f"tablas permitidas: {at}. Para tipos y DDL exactos, usa get_schema_info si está disponible.\n"
        )
    _context_prompt_base: str | None = (effective_prompt + _schema_digest) if _cp.get("enabled") else None

    context_monitor_node = _build_context_monitor_node(
        pruning_config=_cp,
        prompt_base=_context_prompt_base or effective_prompt,
        llm_summary=llm_summary,
        identity_fields=_identity_fields,
    ) if use_cm else None

    tools_sandbox_off = filter_tools_for_sandbox(tools, enabled=False)
    tools_by_name_sandbox_off = {t.name: t for t in tools_sandbox_off}

    _groq_bind = (provider or "").strip().lower() == "groq"
    _mlx_bind = (provider or "").strip().lower() in ("mlx", "iotcorelabs")
    _tools_for_llm_bind = _groq_tools_without_reddit_for_bind(tools) if _groq_bind else tools
    _tools_sandbox_off_bind = (
        _groq_tools_without_reddit_for_bind(tools_sandbox_off) if _groq_bind else tools_sandbox_off
    )
    if _mlx_bind:
        _tools_for_llm_bind = _mlx_tools_for_bind(_tools_for_llm_bind)
        _tools_sandbox_off_bind = _mlx_tools_for_bind(_tools_sandbox_off_bind)
        _log.info(
            "MLX: bind cap %d tools (sandbox_off %d) para caber en budget Metal.",
            len(_tools_for_llm_bind),
            len(_tools_sandbox_off_bind),
        )
    if _groq_bind:
        _log.info(
            "Groq: bind genérico sin reddit_* (%d tools; forzados Reddit/otros usan set acorde).",
            len(_tools_for_llm_bind),
        )

    context_guard_config = getattr(spec, "context_guard_config", None) or {}
    ctx.context_guard_enabled = (
        bool(context_guard_config.get("enabled", False))
        and "catalog_retriever" in (spec.skills_list or [])
    )
    ctx.context_guard_max_retries = int(context_guard_config.get("max_retries", 2))
    ctx.prompt_policies = prompt_policies
    ctx.system_prompt = system_prompt
    ctx.tools = tools
    ctx.tools_by_name = tools_by_name
    ctx.provider = provider
    ctx.model = model
    ctx.base_url = base_url
    ctx.llm = llm
    ctx.llm_fallback = llm_fallback
    ctx.llm_summary = llm_summary
    ctx.effective_prompt = effective_prompt
    ctx.logical_worker_id = _lid
    ctx.context_pruning = _cp
    ctx.use_context_monitor = use_cm
    ctx.context_prompt_base = _context_prompt_base
    ctx.context_monitor_node = context_monitor_node
    ctx.tools_sandbox_off = tools_sandbox_off
    ctx.tools_by_name_sandbox_off = tools_by_name_sandbox_off
    ctx.groq_bind = _groq_bind
    ctx.tools_for_llm_bind = _tools_for_llm_bind
    ctx.tools_sandbox_off_bind = _tools_sandbox_off_bind
    if llm is not None:
        build_agent_llm_bind(ctx)
    _manifest_max_rounds = getattr(spec, "agent_node_max_tool_rounds", None)
    if _manifest_max_rounds:
        ctx.max_tool_rounds = max(1, int(_manifest_max_rounds))
    return ctx
