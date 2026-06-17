"""Invoke-worker node: delegate to subagent graph."""

from __future__ import annotations

import logging
import time
import threading
from typing import Any, Callable

from langchain_core.runnables import RunnableConfig

from duckclaw.forge.rag.context_blocks import preserve_context_blocks_for_worker
from duckclaw.graphs.agent_resilience import (
    classify_exception_for_replan,
    merge_failure_reasons,
    replan_enabled,
)
from duckclaw.graphs.subagent_run_id import acquire_subagent_slot, release_subagent_slot
from duckclaw.manager import manager_worker_cache as _worker_cache_mod
from duckclaw.manager.fast_plans import _manager_visual_generation_intent
from duckclaw.manager.manager_entry_routes import _worker_should_use_url_research_mcp_surface
from duckclaw.manager.manager_invoke_helpers import (
    build_invoke_worker_output,
    build_worker_cache_key,
    compute_invoke_suspend_flags,
    evaluate_worker_replan,
    finalize_invoke_worker_cleanup,
    format_worker_reply,
    prepare_worker_invoke_state,
    resolve_invoke_assigned_worker,
    schedule_delegation_heartbeat_if_needed,
)
from duckclaw.manager.manager_vault_config import _agent_config_db_for_vault
from duckclaw.manager.resilience_flow import (
    _initial_replan_state,
)
from duckclaw.manager.task_activity import _task_summary_for_activity
from duckclaw.manager.task_classification import (
    _incoming_has_context_summary_system_directive,
    _worker_should_use_lite_stdio_mcp_surface,
)
from duckclaw.utils.langsmith_trace import get_tracing_config
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_sys, set_log_context
from duckclaw.workers.factory import explicit_duckdb_schema_request, list_workers

_log = logging.getLogger(__name__)
_obs = get_obs_logger()


def build_invoke_worker_node(
    *,
    db: Any,
    llm: Any | None,
    troot: Any,
    db_path: str,
    llm_provider: str | None,
    llm_model: str | None,
    llm_base_url: str | None,
) -> Callable[[ManagerAgentState, RunnableConfig], ManagerAgentState]:
    from duckclaw.graphs.activity import set_busy, set_idle
    from duckclaw.graphs.on_the_fly_commands import append_task_audit, _resolve_template_id
    from duckclaw.workers.factory import build_worker_graph as _build_worker_graph

    def invoke_worker_node(state: ManagerAgentState, config: RunnableConfig) -> ManagerAgentState:
        """Invoca el grafo del worker asignado; set_busy/set_idle y append_task_audit. Solo invoca si el worker existe en templates."""
        chat_id = state.get("chat_id") or ""
        from duckclaw.graphs.chat_cancel import ChatCancelledError, raise_if_chat_cancelled

        try:
            raise_if_chat_cancelled(str(chat_id or "").strip())
        except ChatCancelledError:
            set_idle(chat_id)
            return {
                "reply": "Interrumpido.",
                "_audit_done": True,
                "assigned_worker_id": (state.get("assigned_worker_id") or "").strip() or None,
            }
        tenant_id = state.get("tenant_id") or "default"
        user_id = state.get("user_id") or chat_id or "default"
        vault_db_path = (state.get("vault_db_path") or "").strip()
        shared_db_path = (state.get("shared_db_path") or "").strip()
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        planned_task = (state.get("planned_task") or "").strip() or incoming
        plan_title = (state.get("plan_title") or "").strip() or None
        history = state.get("history") or []
        available = list(state.get("available_templates") or list_workers(troot, db=db, tenant_id=tenant_id))
        assigned = (state.get("assigned_worker_id") or "").strip() or None
        _all_iw = list_workers(troot, db=db, tenant_id=tenant_id)
        if assigned and assigned not in available and _is_entry_route_system_event(incoming):
            _entry_iw = (state.get("entry_worker_id") or "").strip()
            _c_iw = _resolve_template_id(_all_iw, assigned) or (
                _resolve_template_id(_all_iw, _entry_iw) if _entry_iw else None
            )
            if _c_iw and _c_iw in _all_iw:
                assigned = _c_iw
                if _c_iw not in available:
                    available = list(available) + [_c_iw]
        if assigned not in available:
            assigned = available[0] if available else None
        if assigned:
            try:
                from duckclaw.vaults import resolve_template_vault_path
                from duckclaw.workers.manifest import load_manifest

                _spec_del = load_manifest(assigned)
                _tpl_vault = resolve_template_vault_path(
                    _spec_del.forge_vault_binding, user_id
                )
                if _tpl_vault:
                    vault_db_path = _tpl_vault
            except Exception:
                pass
        if assigned is None:
            set_idle(chat_id)
            _log.warning("manager: no hay plantillas de worker disponibles en %s", getattr(troot, "__str__", lambda: "")() or "forge/templates")
            # No incluir "messages": None — add_messages en ManagerAgentState exige valores no nulos.
            return {
                "reply": "No hay plantillas de worker configuradas. Añade al menos una en forge/templates (con manifest.yaml).",
                "_audit_done": True,
                "assigned_worker_id": None,
            }
        task_summary = (state.get("task_summary") or "").strip() or _task_summary_for_activity(incoming, planned_task)
        planned_task_for_worker = preserve_context_blocks_for_worker(
            incoming,
            planned_task,
            explicit_storage_request=explicit_duckdb_schema_request,
        )
        _combined = planned_task_for_worker or incoming
        _lite_stdio_mcp = _worker_should_use_lite_stdio_mcp_surface(_combined)
        _url_research_mcp = _worker_should_use_url_research_mcp_surface(_combined)
        _visual_lite_mcp = _manager_visual_generation_intent(_combined)
        _summarize_vault_ro = _incoming_has_context_summary_system_directive(_combined)
        t0 = time.monotonic()
        reply = ""
        messages = None
        worker_invoke: dict[str, Any] | None = None
        status = "SUCCESS"
        agent_instance_label = ""
        slot_token = ""
        run_label_n = 1
        raw_worker_reply = ""
        worker_graph = None
        worker_cache_key = ""
        _suspend_for_rw_worker = False
        _suspend_hub_for_visual_delta = False
        _will_suspend_ro = False
        _vault_lock_obj: threading.Lock | None = None
        pa = int(state.get("plan_attempt_index") or 0)
        max_a = int(state.get("plan_max_attempts") or _initial_replan_state()["plan_max_attempts"])
        reasons_acc = list(state.get("plan_failure_reasons") or [])
        _tools_list: list[str] = []
        replan_after = False
        exhausted_final = False
        next_plan_attempt = pa
        try:
            slot_token, run_label_n = acquire_subagent_slot(tenant_id, assigned, str(chat_id or ""))
            agent_instance_label = f"{assigned} {run_label_n}".strip()
            worker_cache_key = (
                f"{tenant_id}::{assigned}::{vault_db_path or db_path or ''}::{shared_db_path}"
                f"::{(llm_provider or '').strip()}::{(llm_model or '').strip()}::{(llm_base_url or '').strip()}"
            )
            if _visual_lite_mcp:
                worker_cache_key = f"{worker_cache_key}::vis_gen"
            elif _lite_stdio_mcp:
                worker_cache_key = f"{worker_cache_key}::ctx_syn"
            elif _url_research_mcp:
                low_url = (_combined or "").strip().lower()
                _url_tag = "reddit" if "reddit.com" in low_url else ("mql5" if "mql5.com" in low_url else "url")
                worker_cache_key = f"{worker_cache_key}::url_{_url_tag}"
            else:
                # No mezclar grafos con Reddit MCP (cold start npx) y turnos sin Reddit.
                low_full = (_combined or "").strip().lower()
                worker_cache_key = (
                    f"{worker_cache_key}::mcp_rd"
                    if "reddit.com" in low_full
                    else f"{worker_cache_key}::lean_full"
                )
            if _summarize_vault_ro:
                worker_cache_key = f"{worker_cache_key}::sum_vault_ro"
            from duckclaw.workers.factory import _get_db_path, _same_duckdb_file
            from duckclaw.workers.manifest import load_manifest

            spec_inv = load_manifest(assigned, troot, db=db, tenant_id=tenant_id)
            mgr_path = str(getattr(db, "_path", "") or "").strip()
            worker_resolved = _get_db_path(
                assigned, tenant_id, (vault_db_path or db_path or None)
            ).strip()
            _mgr_read_only = bool(getattr(db, "_read_only", False))
            # Misma resolución que build_worker_graph; vault_db_path crudo puede diverger del path real.
            _needs_rw_vault = (not bool(spec_inv.read_only)) and (not bool(_summarize_vault_ro))
            _hub_same_as_worker = bool(
                worker_resolved and mgr_path and _same_duckdb_file(mgr_path, worker_resolved)
            )
            _shared_resolved_inv = ""
            try:
                from duckclaw.workers.factory import _resolve_shared_db_path

                _shared_resolved_inv = (_resolve_shared_db_path(spec_inv, shared_db_path or None) or "").strip()
            except Exception:
                pass
            _will_skip_private = bool(
                not _mgr_read_only
                and _hub_same_as_worker
                and not _shared_resolved_inv
                and not _summarize_vault_ro
            )
            # DuckDB: no RO+RW simultáneo al mismo archivo. Suspender el RO del manager antes
            # de abrir el worker RW; leer sandbox/chat_state antes (sin worker RW abierto).
            _suspend_for_rw_worker = bool(
                _mgr_read_only and _needs_rw_vault and _hub_same_as_worker
            )
            # VISUAL_ASSET_UPSERT escribe en hub (get_gateway_db_path), no en vault del worker.
            # El manager mantiene RO al hub durante ComfyUI (~3–4 min); suspender evita lock con db-writer.
            _suspend_hub_for_visual_delta = bool(
                _mgr_read_only and _visual_lite_mcp and mgr_path
            )
            _will_suspend_ro = _suspend_for_rw_worker or _suspend_hub_for_visual_delta
            _spawn_inline_writes = False
            try:
                from duckclaw.spawn_profile import spawn_inline_writes_enabled

                _spawn_inline_writes = bool(spawn_inline_writes_enabled())
            except Exception:
                pass
            # Serializa acceso al .duckdb: dos webhooks concurrentes no deben abrir dos DuckClaw RW.
            _vk = _worker_cache_mod._vault_lock_key(worker_resolved)
            if _vk:
                with _worker_cache_mod._vault_invoke_guard:
                    if _vk not in _worker_cache_mod._vault_invoke_locks:
                        _worker_cache_mod._vault_invoke_locks[_vk] = threading.Lock()
                    _vault_lock_obj = _worker_cache_mod._vault_invoke_locks[_vk]
                _vault_lock_obj.acquire()
            _cfg_db = _agent_config_db_for_vault(db, vault_db_path or None)
            from duckclaw.runtime_session_settings import resolve_session_runtime_setting

            raw_sb = resolve_session_runtime_setting(
                _cfg_db,
                chat_id,
                "sandbox_enabled",
                tenant_id=tenant_id,
            )
            sb_on = (raw_sb or "").strip().lower() in ("true", "1", "on", "sí", "si")
            db_display = vault_db_path or db_path or "(unknown)"
            if _will_suspend_ro:
                db.suspend_readonly_file_handle()
            if _visual_lite_mcp:
                try:
                    from duckclaw.forge.skills.visual_state_delta import set_visual_state_delta_hub_db

                    set_visual_state_delta_hub_db(db)
                except Exception:
                    pass
            try:
                from duckclaw.forge.skills.visual_provider import resolve_visual_provider

                _vis_prov = resolve_visual_provider(_cfg_db, chat_id)
            except Exception:
                _vis_prov = "local"
            worker_cache_key = f"{worker_cache_key}::visprov_{_vis_prov}"
            if worker_cache_key not in _worker_cache_mod._worker_graph_cache:
                _worker_cache_mod._worker_graph_cache[worker_cache_key] = _build_worker_graph(
                    assigned,
                    vault_db_path or db_path,
                    llm,
                    templates_root=troot,  # None => forge/templates
                    llm_provider=llm_provider or "",
                    llm_model=llm_model or "",
                    llm_base_url=llm_base_url or "",
                    instance_name=tenant_id,  # Aislar por tenant (Forge/WorkerFactory)
                    shared_db_path=shared_db_path or None,
                    reuse_db=db,
                    db=db,
                    tenant_id=tenant_id,
                    tool_surface=(
                        "visual_generation"
                        if _visual_lite_mcp
                        else (
                            "context_synthesis"
                            if _lite_stdio_mcp
                            else ("url_research" if _url_research_mcp else "full")
                        )
                    ),
                    incoming_hint=_combined,
                    open_vault_read_only=_summarize_vault_ro,
                )
            worker_graph = _worker_cache_mod._worker_graph_cache[worker_cache_key]
            set_log_context(
                tenant_id=tenant_id,
                worker_id=assigned,
                chat_id=format_chat_log_identity(chat_id or "unknown", state.get("username")),
            )
            log_sys(_obs, "Delegación: manager -> %s", assigned)
            log_sys(
                _obs,
                "Sandbox: %s | DB: %s",
                "ON" if sb_on else "OFF",
                db_display,
            )
            # Pasar la tarea planificada al worker para que use herramientas y no responda genérico
            # Incluimos chat_id para que el worker pueda leer sandbox_enabled por sesión.
            worker_state = prepare_worker_invoke_state(
                state=state,
                planned_task_for_worker=planned_task_for_worker,
                incoming=incoming,
                history=history,
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                vault_db_path=vault_db_path,
                shared_db_path=shared_db_path,
                agent_instance_label=agent_instance_label,
                plan_title=plan_title,
                pa=pa,
                max_a=max_a,
                assigned=assigned,
            )
            trace_cfg = get_tracing_config(
                tenant_id,
                assigned,
                str(chat_id or "unknown"),
                base=config,
            )
            schedule_delegation_heartbeat_if_needed(
                state=state,
                chat_id=chat_id,
                tenant_id=tenant_id,
                user_id=user_id,
                task_summary=task_summary,
                agent_instance_label=agent_instance_label,
                plan_title=plan_title,
                assigned=assigned,
            )
            try:
                raise_if_chat_cancelled(str(chat_id or "").strip())
                worker_invoke = worker_graph.invoke(worker_state, trace_cfg)
            except ChatCancelledError:
                set_idle(chat_id)
                return {
                    "reply": "Interrumpido.",
                    "_audit_done": True,
                    "assigned_worker_id": str(assigned or "").strip() or None,
                }
            _wdb_peek = getattr(worker_graph, "_worker_db", None)
            if _wdb_peek is not None and _wdb_peek is not db:
                _peek_rw = not bool(getattr(_wdb_peek, "_read_only", False))
                if _suspend_for_rw_worker or _peek_rw:
                    _worker_cache_mod._release_worker_db_handle(worker_graph, cache_key=worker_cache_key)
            raw_worker_reply = str(
                worker_invoke.get("internal_reply")
                or worker_invoke.get("reply")
                or worker_invoke.get("output")
                or "Sin respuesta."
            )
            reply = format_worker_reply(
                raw_worker_reply=raw_worker_reply,
                assigned=assigned,
                run_label_n=run_label_n,
                chat_id=chat_id,
                visual_lite_mcp=_visual_lite_mcp,
                worker_invoke=worker_invoke if isinstance(worker_invoke, dict) else None,
            )
            messages = worker_invoke.get("messages")
            if isinstance(messages, tuple):
                messages = list(messages)
            _replan = evaluate_worker_replan(
                worker_invoke=worker_invoke,
                raw_worker_reply=raw_worker_reply,
                messages=messages,
                combined=_combined,
                spec_inv=spec_inv,
                status=status,
                pa=pa,
                max_a=max_a,
                reasons_acc=reasons_acc,
            )
            _tools_list = _replan.tools_list
            replan_after = _replan.replan_after
            exhausted_final = _replan.exhausted_final
            next_plan_attempt = _replan.next_plan_attempt
            reasons_acc = _replan.reasons_acc
            _log.info(
                "manager tool_use: delegó a worker=%s | tools usadas=%s",
                assigned,
                _tools_list if _tools_list else "ninguna",
            )
        except Exception as e:
            msg = str(e)[:2048]
            low = msg.lower()
            # DuckDB usa "Connection Error" al mezclar RO/RW en el mismo archivo; no confundir con MLX caído.
            _duckdb_config_clash = (
                "same database file" in low and "different configuration" in low
            ) or ("duckdb" in low and "read_only" in low)
            if (
                not _duckdb_config_clash
                and any(
                    x in low
                    for x in (
                        "connection error",
                        "connection refused",
                        "remote protocol",
                        "failed to establish",
                        "errno 61",
                        "econnrefused",
                    )
                )
            ):
                msg = (
                    "El backend de inferencia (p. ej. MLX en :8080) no está disponible o se reinició; "
                    "suele ir ligado a OOM en Metal. Revisa `pm2 logs MLX-Inference` y, si usas resúmenes largos "
                    "de contexto, reduce `DUCKCLAW_SEMANTIC_SUMMARY_MAX_CHARS`.\n\n"
                    f"Detalle: {str(e)[:400]}"
                )
            reply = format_worker_reply(
                raw_worker_reply=msg,
                assigned=assigned,
                run_label_n=run_label_n,
                chat_id=chat_id,
                visual_lite_mcp=False,
                worker_invoke=None,
            )
            status = "FAILED"
            _retryable, _rreason = classify_exception_for_replan(e, _duckdb_config_clash)
            if replan_enabled() and _retryable:
                reasons_acc = merge_failure_reasons(reasons_acc, _rreason)
                if pa + 1 < max_a:
                    replan_after = True
                    next_plan_attempt = pa + 1
                    log_sys(
                        _obs,
                        "manager replan: excepción recuperable -> intento %s/%s (%s)",
                        pa + 2,
                        max_a,
                        _rreason,
                    )
                else:
                    exhausted_final = True
        finally:
            finalize_invoke_worker_cleanup(
                worker_graph=worker_graph,
                db=db,
                suspend_for_rw_worker=_suspend_for_rw_worker,
                worker_cache_key=worker_cache_key,
                visual_lite_mcp=_visual_lite_mcp,
                slot_token=slot_token,
                tenant_id=tenant_id,
                assigned=assigned,
                chat_id=chat_id,
                t0=t0,
                status=status,
                plan_title=plan_title,
                incoming=incoming,
                will_suspend_ro=_will_suspend_ro,
                vault_lock_obj=_vault_lock_obj,
            )

        return build_invoke_worker_output(
            exhausted_final=exhausted_final,
            reasons_acc=reasons_acc,
            reply=reply,
            assigned=assigned,
            plan_title=plan_title,
            messages=messages,
            worker_invoke=worker_invoke,
            raw_worker_reply=raw_worker_reply,
            state=state,
            max_a=max_a,
            replan_after=replan_after,
            next_plan_attempt=next_plan_attempt,
        )

    return invoke_worker_node
