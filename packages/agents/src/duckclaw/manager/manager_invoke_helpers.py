"""Pure helpers for invoke-worker: assignment, cache keys, suspend flags, replan."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, Callable

from duckclaw.graphs.agent_resilience import (
    merge_failure_reasons,
    replan_enabled,
    worker_reply_suggests_replan_without_tools,
)
from duckclaw.manager.manager_entry_routes import _is_entry_route_system_event
from duckclaw.manager.manager_worker_cache import (
    _vault_invoke_guard,
    _vault_invoke_locks,
    _vault_lock_key,
)
from duckclaw.manager.routing import _worker_matches_id
from duckclaw.manager.task_activity import _worker_tool_names_from_messages
from duckclaw.manager.worker_reply_formatting import _prepend_subagent_label_once
from duckclaw.utils.logger import get_obs_logger, log_sys

_obs = get_obs_logger()


@dataclass
class InvokeSuspendFlags:
    suspend_for_rw_worker: bool
    suspend_hub_for_visual_delta: bool
    will_suspend_ro: bool
    vault_lock_obj: threading.Lock | None


def resolve_invoke_assigned_worker(
    state: dict[str, Any],
    *,
    assigned: str | None,
    available: list[str],
    incoming: str,
    all_workers: list[str],
    resolve_template_id: Callable[[list[str], str], str | None],
) -> tuple[str | None, list[str]]:
    if assigned and assigned not in available and _is_entry_route_system_event(incoming):
        entry_iw = (state.get("entry_worker_id") or "").strip()
        canon = resolve_template_id(all_workers, assigned) or (
            resolve_template_id(all_workers, entry_iw) if entry_iw else None
        )
        if canon and canon in all_workers:
            assigned = canon
            if canon not in available:
                available = list(available) + [canon]
    if assigned not in available:
        assigned = available[0] if available else None
    return assigned, available


def build_worker_cache_key(
    *,
    tenant_id: str,
    assigned: str,
    vault_db_path: str,
    db_path: str,
    shared_db_path: str,
    llm_provider: str | None,
    llm_model: str | None,
    llm_base_url: str | None,
    combined: str,
    visual_lite_mcp: bool,
    lite_stdio_mcp: bool,
    url_research_mcp: bool,
    summarize_vault_ro: bool,
    vis_prov: str,
) -> str:
    worker_cache_key = (
        f"{tenant_id}::{assigned}::{vault_db_path or db_path or ''}::{shared_db_path}"
        f"::{(llm_provider or '').strip()}::{(llm_model or '').strip()}::{(llm_base_url or '').strip()}"
    )
    if visual_lite_mcp:
        worker_cache_key = f"{worker_cache_key}::vis_gen"
    elif lite_stdio_mcp:
        worker_cache_key = f"{worker_cache_key}::ctx_syn"
    elif url_research_mcp:
        low_url = (combined or "").strip().lower()
        url_tag = "reddit" if "reddit.com" in low_url else ("mql5" if "mql5.com" in low_url else "url")
        worker_cache_key = f"{worker_cache_key}::url_{url_tag}"
    else:
        low_full = (combined or "").strip().lower()
        worker_cache_key = (
            f"{worker_cache_key}::mcp_rd" if "reddit.com" in low_full else f"{worker_cache_key}::lean_full"
        )
    if summarize_vault_ro:
        worker_cache_key = f"{worker_cache_key}::sum_vault_ro"
    return f"{worker_cache_key}::visprov_{vis_prov}"


def compute_invoke_suspend_flags(
    *,
    db: Any,
    spec_inv: Any,
    mgr_path: str,
    worker_resolved: str,
    shared_db_path: str | None,
    summarize_vault_ro: bool,
    visual_lite_mcp: bool,
) -> InvokeSuspendFlags:
    from duckclaw.workers.factory import _resolve_shared_db_path, _same_duckdb_file

    mgr_read_only = bool(getattr(db, "_read_only", False))
    needs_rw_vault = (not bool(spec_inv.read_only)) and (not bool(summarize_vault_ro))
    hub_same_as_worker = bool(worker_resolved and mgr_path and _same_duckdb_file(mgr_path, worker_resolved))
    shared_resolved = ""
    try:
        shared_resolved = (_resolve_shared_db_path(spec_inv, shared_db_path or None) or "").strip()
    except Exception:
        pass
    suspend_for_rw_worker = bool(mgr_read_only and needs_rw_vault and hub_same_as_worker)
    suspend_hub_for_visual_delta = bool(mgr_read_only and visual_lite_mcp and mgr_path)
    will_suspend_ro = suspend_for_rw_worker or suspend_hub_for_visual_delta
    vault_lock_obj: threading.Lock | None = None
    vk = _vault_lock_key(worker_resolved)
    if vk:
        with _vault_invoke_guard:
            if vk not in _vault_invoke_locks:
                _vault_invoke_locks[vk] = threading.Lock()
            vault_lock_obj = _vault_invoke_locks[vk]
        vault_lock_obj.acquire()
    return InvokeSuspendFlags(
        suspend_for_rw_worker=suspend_for_rw_worker,
        suspend_hub_for_visual_delta=suspend_hub_for_visual_delta,
        will_suspend_ro=will_suspend_ro,
        vault_lock_obj=vault_lock_obj,
    )


def format_worker_reply(
    *,
    raw_worker_reply: str,
    assigned: str,
    run_label_n: int,
    chat_id: str,
    visual_lite_mcp: bool,
    worker_invoke: dict[str, Any] | None,
) -> str:
    reply = raw_worker_reply
    label_reply = f"{assigned} {run_label_n}".strip()
    crm = str(chat_id or "").strip().lower().startswith("crm-ticket-")
    if visual_lite_mcp and isinstance(worker_invoke, dict):
        vis_b64 = (worker_invoke.get("sandbox_photo_base64") or "").strip()
        vis_aid = (worker_invoke.get("visual_artifact_id") or "").strip()
        if vis_b64 or vis_aid:
            short_vis = (raw_worker_reply or "").strip()
            if not short_vis or len(short_vis) > 240:
                short_vis = "Imagen generada."
            reply = short_vis
    if not crm:
        reply = _prepend_subagent_label_once(reply, label_reply)
    return reply


@dataclass
class ReplanDecision:
    replan_after: bool
    exhausted_final: bool
    next_plan_attempt: int
    reasons_acc: list[str]
    tools_list: list[str]


def evaluate_worker_replan(
    *,
    worker_invoke: dict[str, Any],
    raw_worker_reply: str,
    messages: Any,
    combined: str,
    spec_inv: Any,
    status: str,
    pa: int,
    max_a: int,
    reasons_acc: list[str],
) -> ReplanDecision:
    tools_list = _worker_tool_names_from_messages(messages if isinstance(messages, list) else None)
    replan_after = False
    exhausted_final = False
    next_plan_attempt = pa
    if not (replan_enabled() and status == "SUCCESS"):
        return ReplanDecision(replan_after, exhausted_final, next_plan_attempt, reasons_acc, tools_list)

    w_llm_failed = bool(worker_invoke.get("_duckclaw_worker_llm_invoke_failed"))
    w_llm_transient = bool(worker_invoke.get("_duckclaw_worker_llm_transient"))
    soft_would_match = worker_reply_suggests_replan_without_tools(raw_worker_reply)

    if w_llm_failed and w_llm_transient:
        fk = (worker_invoke.get("_duckclaw_worker_llm_failure_kind") or "error").strip()
        rworker = f"inferencia: fallo de conexión al backend LLM en el worker ({fk})"
        reasons_acc = merge_failure_reasons(reasons_acc, rworker)
        if pa + 1 < max_a:
            replan_after = True
            next_plan_attempt = pa + 1
            log_sys(_obs, "manager replan: worker LLM transitorio -> intento %s/%s (%s)", pa + 2, max_a, rworker)
        else:
            exhausted_final = True
    elif w_llm_failed and not w_llm_transient:
        reasons_acc = merge_failure_reasons(
            reasons_acc,
            "inferencia: error no transitorio en invoke del worker "
            f"({(worker_invoke.get('_duckclaw_worker_llm_failure_kind') or 'unknown')})",
        )
    else:
        try:
            from duckclaw.workers.tool_orchestration import parse_tool_orchestration, replan_rule_triggered

            orch_replan = parse_tool_orchestration(spec_inv)
            if orch_replan:
                orch_trig, orch_reason = replan_rule_triggered(orch_replan, combined, tools_list)
                if orch_trig:
                    reasons_acc = merge_failure_reasons(reasons_acc, orch_reason)
                    if pa + 1 < max_a:
                        replan_after = True
                        next_plan_attempt = pa + 1
                        log_sys(
                            _obs,
                            "manager replan: tool_orchestration -> intento %s/%s (%s)",
                            pa + 2,
                            max_a,
                            orch_reason,
                        )
                    else:
                        exhausted_final = True
        except Exception:
            pass
        if not replan_after and not tools_list and soft_would_match:
            rsoft = "inferencia: respuesta sin tools con indicios de fallo de backend"
            reasons_acc = merge_failure_reasons(reasons_acc, rsoft)
            if pa + 1 < max_a:
                replan_after = True
                next_plan_attempt = pa + 1
                log_sys(_obs, "manager replan: señal débil (sin tools) -> intento %s/%s", pa + 2, max_a)
            else:
                exhausted_final = True

    return ReplanDecision(replan_after, exhausted_final, next_plan_attempt, reasons_acc, tools_list)


def prepare_worker_invoke_state(
    *,
    state: dict[str, Any],
    planned_task_for_worker: str,
    incoming: str,
    history: list[Any],
    chat_id: str,
    tenant_id: str,
    user_id: str,
    vault_db_path: str,
    shared_db_path: str,
    agent_instance_label: str,
    plan_title: str | None,
    pa: int,
    max_a: int,
    assigned: str,
) -> dict[str, Any]:
    import time

    out_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None
    worker_state: dict[str, Any] = {
        "input": planned_task_for_worker,
        "incoming": planned_task_for_worker,
        "user_incoming": (state.get("user_incoming") or incoming or "").strip(),
        "history": history,
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "username": (state.get("username") or "").strip(),
        "vault_db_path": vault_db_path,
        "shared_db_path": shared_db_path,
        "subagent_instance_label": agent_instance_label,
        "heartbeat_plan_title": (plan_title or "").strip(),
        "subagent_turn_started_monotonic": time.monotonic(),
        "plan_attempt_index": pa,
        "plan_max_attempts": max_a,
    }
    if out_tok:
        worker_state["outbound_telegram_bot_token"] = out_tok
    mission = state.get("active_mission")
    if isinstance(mission, dict) and _worker_matches_id(assigned, mission.get("target_worker")):
        worker_state["suppress_subagent_egress"] = True
        try:
            from duckclaw.graphs.chat_heartbeat import schedule_chat_heartbeat_dm

            target_name = str(mission.get("target_worker") or assigned or "subagente")
            source_name = str(mission.get("source_worker") or "manager")
            handoff_msg = (
                f"A2A handoff visible: @{target_name}, solicitado por @{source_name} "
                "para misión en curso."
            )
            schedule_chat_heartbeat_dm(
                str(tenant_id or "default").strip() or "default",
                str(chat_id or "").strip(),
                str(user_id or "").strip() or str(chat_id or "").strip(),
                handoff_msg,
                log_worker_id=agent_instance_label or None,
                log_username=(state.get("username") or "").strip() or None,
                log_plan_title="A2A handoff",
                outbound_bot_token=out_tok,
                routing_worker_id=str(assigned or "").strip() or None,
            )
        except Exception:
            pass
    if state.get("handoff_context"):
        worker_state["handoff_context"] = state.get("handoff_context")
    mission_ctx = (state.get("mission_context_system_message") or "").strip()
    if mission_ctx:
        from langchain_core.messages import SystemMessage

        worker_state["messages"] = [SystemMessage(content=mission_ctx)]
    return worker_state


def schedule_delegation_heartbeat_if_needed(
    *,
    state: dict[str, Any],
    chat_id: str,
    tenant_id: str,
    user_id: str,
    task_summary: str,
    agent_instance_label: str,
    plan_title: str | None,
    assigned: str,
) -> None:
    from duckclaw.graphs.chat_heartbeat import (
        format_delegation_heartbeat_message,
        is_admin_ui_chat_session,
        schedule_chat_heartbeat_dm,
    )

    cid = str(chat_id or "").strip()
    if is_admin_ui_chat_session(cid):
        return
    out_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None
    tasks_for_hb = state.get("tasks")
    hb_text = format_delegation_heartbeat_message(
        state.get("plan_title"),
        tasks_for_hb if isinstance(tasks_for_hb, list) else [],
        task_summary=task_summary,
        subagent_header=agent_instance_label or None,
    )
    schedule_chat_heartbeat_dm(
        str(tenant_id or "default").strip() or "default",
        cid,
        str(user_id or "").strip() or cid,
        hb_text,
        log_worker_id=agent_instance_label or None,
        log_username=(state.get("username") or "").strip() or None,
        log_plan_title=(plan_title or "").strip() or None,
        outbound_bot_token=out_tok,
        routing_worker_id=str(assigned or "").strip() or None,
    )


def finalize_invoke_worker_cleanup(
    *,
    worker_graph: Any,
    db: Any,
    suspend_for_rw_worker: bool,
    worker_cache_key: str,
    visual_lite_mcp: bool,
    slot_token: str | None,
    tenant_id: str,
    assigned: str,
    chat_id: str,
    t0: float,
    status: str,
    plan_title: str | None,
    incoming: str,
    will_suspend_ro: bool,
    vault_lock_obj: threading.Lock | None,
) -> None:
    import time

    from duckclaw.graphs.activity import set_idle
    from duckclaw.graphs.on_the_fly_commands import append_task_audit
    from duckclaw.graphs.subagent_run_id import release_subagent_slot
    from duckclaw.manager import manager_worker_cache as worker_cache_mod

    _wdb = getattr(worker_graph, "_worker_db", None) if worker_graph is not None else None
    _worker_rw = _wdb is not None and not bool(getattr(_wdb, "_read_only", False))
    if _wdb is not None and _wdb is not db and (suspend_for_rw_worker or _worker_rw):
        try:
            _wdb.close()
        except Exception:
            pass
        try:
            worker_cache_mod._worker_graph_cache.pop(worker_cache_key, None)
        except Exception:
            pass
    if visual_lite_mcp:
        try:
            from duckclaw.forge.skills.visual_state_delta import clear_visual_state_delta_hub_db

            clear_visual_state_delta_hub_db()
        except Exception:
            pass
    if slot_token:
        release_subagent_slot(tenant_id, assigned, slot_token, str(chat_id or ""))
    set_idle(chat_id)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    append_task_audit(db, chat_id, assigned, incoming, status, elapsed_ms, plan_title=plan_title)
    if will_suspend_ro:
        try:
            db.resume_readonly_file_handle()
        except Exception:
            pass
    if vault_lock_obj is not None:
        try:
            vault_lock_obj.release()
        except Exception:
            pass


def build_invoke_worker_output(
    *,
    exhausted_final: bool,
    reasons_acc: list[str],
    reply: str,
    assigned: str,
    plan_title: str | None,
    messages: Any,
    worker_invoke: Any,
    raw_worker_reply: str,
    state: dict[str, Any],
    max_a: int,
    replan_after: bool,
    next_plan_attempt: int,
) -> dict[str, Any]:
    from duckclaw.graphs.agent_resilience import format_exhausted_plan_failure
    from duckclaw.graphs.sandbox import extract_latest_sandbox_figure_base64
    from duckclaw.graphs.state import ManagerAgentState
    from duckclaw.manager.resilience_flow import _replan_output_fields

    if exhausted_final:
        reply = format_exhausted_plan_failure(reasons_acc)
    out: ManagerAgentState = {
        "reply": reply,
        "_audit_done": True,
        "assigned_worker_id": assigned,
        "plan_title": plan_title,
    }  # type: ignore[assignment]
    if messages is not None:
        out["messages"] = messages
    b64 = ""
    if isinstance(worker_invoke, dict):
        b64 = (worker_invoke.get("sandbox_photo_base64") or "").strip()
    if not b64 and messages is not None:
        b64 = extract_latest_sandbox_figure_base64(messages) or ""
    if b64:
        out["sandbox_photo_base64"] = b64
    aid = ""
    if isinstance(worker_invoke, dict):
        aid = (worker_invoke.get("visual_artifact_id") or "").strip()
    if aid:
        out["visual_artifact_id"] = aid
    if "active_mission" in state:
        out["active_mission"] = state.get("active_mission")
    if "handoff_context" in state:
        out["handoff_context"] = state.get("handoff_context")
    out["last_worker_raw_reply"] = raw_worker_reply or reply
    out["plan_max_attempts"] = max_a
    out.update(
        _replan_output_fields(
            replan_after=replan_after,
            exhausted_final=exhausted_final,
            next_plan_attempt=next_plan_attempt,
            max_attempts=max_a,
            failure_reasons=reasons_acc,
        )
    )
    return out


__all__ = [
    "InvokeSuspendFlags",
    "ReplanDecision",
    "build_invoke_worker_output",
    "build_worker_cache_key",
    "compute_invoke_suspend_flags",
    "evaluate_worker_replan",
    "finalize_invoke_worker_cleanup",
    "format_worker_reply",
    "prepare_worker_invoke_state",
    "resolve_invoke_assigned_worker",
    "schedule_delegation_heartbeat_if_needed",
]
