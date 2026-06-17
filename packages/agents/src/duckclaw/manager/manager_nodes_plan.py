"""Plan node: task shaping, LLM planner, orchestrator delegate."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from duckclaw.graphs.activity import set_busy
from duckclaw.graphs.state import ManagerAgentState
from duckclaw.manager.fast_plans import _try_capability_fast_plan
from duckclaw.manager.manager_delegation import _resolve_orchestrator_delegate
from duckclaw.manager.manager_entry_routes import _is_entry_route_system_event
from duckclaw.manager.manager_mercenary_policy import (
    _should_disable_mercenary_for_browser_intent,
    _strip_mercenary_spec_for_browser_worker,
)
from duckclaw.manager.manager_plan_task import _plan_task, _sanitize_manager_plan_title
from duckclaw.manager.manager_planner_llm import _llm_plan, _llm_plan_from_model
from duckclaw.manager.manager_vault_config import _agent_config_db_for_vault
from duckclaw.manager.resilience_flow import (
    _initial_replan_state,
    _planned_task_with_replan_suffix,
)
from duckclaw.manager.task_activity import _activity_task_for_plan, _task_summary_for_activity
from duckclaw.manager.task_classification import _incoming_has_context_summary_system_directive
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_plan, log_sys, set_log_context

_log = logging.getLogger(__name__)
_obs = get_obs_logger()


def build_plan_node(
    *,
    db: Any,
    llm: Any | None,
    troot: Any,
    planner_system_prompt: str,
) -> Callable[[ManagerAgentState], ManagerAgentState]:
    from duckclaw.graphs.on_the_fly_commands import _resolve_template_id
    from duckclaw.workers.factory import list_workers

    def plan_node(state: ManagerAgentState) -> ManagerAgentState:
        """Formula un plan/tarea clara, genera plan_title/tasks y conserva la ruta de catálogo."""
        _tid = (state.get("tenant_id") or "default").strip() or "default"
        _cid = (state.get("chat_id") or "").strip() or "unknown"
        set_log_context(
            tenant_id=_tid,
            worker_id="manager",
            chat_id=format_chat_log_identity(_cid, state.get("username")),
        )
        # Preservar incoming por si el estado no lo propaga (fallback: input, message)
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        available_plan = state.get("available_templates") or list_workers(troot, db=db, tenant_id=_tid)
        default_worker = available_plan[0] if available_plan else None
        assigned = (state.get("assigned_worker_id") or default_worker or "").strip() or default_worker
        coordinator_id = (state.get("coordinator_worker_id") or "").strip() or None
        delegation_pool = [str(x).strip() for x in (state.get("delegation_pool") or []) if str(x).strip()]
        if not incoming:
            _log.warning("manager plan: incoming vacío en state (keys=%s)", list(state.keys()))

        _vault_path_plan = (state.get("vault_db_path") or "").strip()
        _plan_cfg_db = _agent_config_db_for_vault(db, _vault_path_plan or None)
        _plan_prompt_policies = PromptPolicyResolver(_plan_cfg_db)
        _orch_affirm: tuple[str, list[str], str, str] | None = None
        _capability_fast: tuple[str, list[str], str, str] | None = None
        if incoming:
            try:
                from duckclaw.workers.manifest import load_manifest
                from duckclaw.workers.tool_orchestration import try_manifest_affirm_followup

                _spec_affirm = load_manifest(assigned, troot)
                _orch_affirm = try_manifest_affirm_followup(
                    incoming,
                    state.get("history"),
                    assigned,
                    _spec_affirm,
                )
            except Exception:
                _orch_affirm = None
        if incoming and not _orch_affirm:
            _capability_fast = _try_capability_fast_plan(
                incoming,
                [str(x) for x in (available_plan or []) if x],
                db=_plan_cfg_db,
                tenant_id=_tid,
            )
        if _orch_affirm:
            plan_title, tasks, _inject_orch, _ov_orch = _orch_affirm
            mercenary_spec = None
        elif _capability_fast:
            plan_title, tasks, _inject_fast, _ov_fast = _capability_fast
            mercenary_spec = None
        else:
            _psp = (planner_system_prompt or "").strip()
            mercenary_spec = None
            if _incoming_has_context_summary_system_directive(incoming):
                plan_title, tasks = _llm_plan(incoming)
            elif llm is not None and _psp:
                _parsed = _llm_plan_from_model(llm, incoming, _psp)
                if _parsed:
                    plan_title, tasks, mercenary_spec, _delegate_unused = _parsed
                else:
                    plan_title, tasks = _llm_plan(incoming)
                    mercenary_spec = None
            else:
                plan_title, tasks = _llm_plan(incoming)

            plan_title = _sanitize_manager_plan_title(plan_title, incoming, assigned)

        _plan_chat_id = (state.get("chat_id") or "").strip() or None
        if mercenary_spec is not None and _should_disable_mercenary_for_browser_intent(
            incoming, tasks, plan_title, chat_id=_plan_chat_id
        ):
            mercenary_spec = None

        override_worker: Optional[str] = None
        # Mantener lógica existente de ruteo / planned_task
        if _orch_affirm:
            if _ov_orch and _ov_orch in (available_plan or []):
                assigned = _ov_orch
            override_worker = _ov_orch
            planned = _inject_orch
            planned_final = _inject_orch
        elif _capability_fast:
            if _ov_fast and _ov_fast in (available_plan or []):
                assigned = _ov_fast
            override_worker = _ov_fast
            planned = _inject_fast
            planned_final = _inject_fast
        else:
            planned, override_worker = _plan_task(
                incoming,
                assigned,
                prompt_policies=_plan_prompt_policies,
            )
            planned_final = planned or incoming
        _pa_plan = int(state.get("plan_attempt_index") or 0)
        _max_plan = int(state.get("plan_max_attempts") or _initial_replan_state()["plan_max_attempts"])
        planned_final = _planned_task_with_replan_suffix(planned_final, _pa_plan, _max_plan)

        if coordinator_id and delegation_pool and not _orch_affirm and not _capability_fast:
            assigned = _resolve_orchestrator_delegate(
                incoming,
                delegation_pool,
                coordinator_id,
                llm,
                (planner_system_prompt or "").strip(),
                troot,
            )
            _coord_prefix = f"[Coordinado por {coordinator_id}] "
            if not (planned_final or "").strip().startswith(_coord_prefix):
                planned_final = _coord_prefix + (planned_final or incoming).strip()
            log_sys(
                _obs,
                "AXIS coordinador %s → delegado %s",
                coordinator_id,
                assigned,
            )

        # Derivar task_summary a partir del mensaje original / planned_task
        task_summary = _task_summary_for_activity(incoming, planned_final)

        user_incoming = (state.get("user_incoming") or incoming or "").strip()

        out: ManagerAgentState = {
            "planned_task": planned_final,
            "incoming": incoming,
            "user_incoming": user_incoming,
            "task_summary": task_summary,
            "plan_title": plan_title or None,
            "tasks": tasks or [],
            "replan_requested": False,
        }  # type: ignore[assignment]
        if mercenary_spec:
            out["mercenary_spec"] = mercenary_spec
        if isinstance(state.get("handoff_context"), dict):
            out["handoff_context"] = state.get("handoff_context")
        if isinstance(state.get("active_mission"), dict):
            out["active_mission"] = state.get("active_mission")

        if coordinator_id and delegation_pool:
            out["coordinator_worker_id"] = coordinator_id
            out["delegation_pool"] = delegation_pool
            if assigned:
                out["assigned_worker_id"] = assigned
        elif override_worker and override_worker in available_plan:
            out["assigned_worker_id"] = override_worker
        elif assigned not in available_plan and available_plan:
            out["assigned_worker_id"] = available_plan[0]
        else:
            out["assigned_worker_id"] = assigned

        route_entry = (state.get("entry_worker_id") or "").strip()
        if route_entry and _is_entry_route_system_event(incoming):
            _all_plan_disk = list_workers(troot, db=db, tenant_id=_tid)
            _canon_re = _resolve_template_id(_all_plan_disk, route_entry)
            if _canon_re and _canon_re in _all_plan_disk:
                out["assigned_worker_id"] = _canon_re
                if _canon_re not in available_plan:
                    available_plan = list(available_plan) + [_canon_re]
        elif route_entry:
            _all_plan_disk = list_workers(troot, db=db, tenant_id=_tid)
            _canon_play = _resolve_template_id(_all_plan_disk, route_entry)
            if _canon_play and _canon_play in _all_plan_disk:
                out["assigned_worker_id"] = _canon_play
                if _canon_play not in available_plan:
                    available_plan = list(available_plan) + [_canon_play]

        if _strip_mercenary_spec_for_browser_worker(out, troot):
            mercenary_spec = None

        out["available_templates"] = available_plan
        # Preservar estado para invoke_worker
        out["incoming"] = incoming or state.get("incoming") or state.get("input") or state.get("message") or ""
        out["input"] = out["incoming"]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        if "tenant_id" in state:
            out["tenant_id"] = state["tenant_id"]
        if "user_id" in state:
            out["user_id"] = state["user_id"]
        if "vault_db_path" in state:
            out["vault_db_path"] = state["vault_db_path"]
        if "shared_db_path" in state:
            out["shared_db_path"] = state["shared_db_path"]
        if "username" in state:
            out["username"] = state["username"]
        _ot_p = (state.get("outbound_telegram_bot_token") or "").strip()
        if _ot_p:
            out["outbound_telegram_bot_token"] = _ot_p
        if "active_mission" in state and not out.get("active_mission"):
            out["active_mission"] = state.get("active_mission")
        # Actualizar activity para /tasks usando solo el título del plan cuando esté disponible
        activity_task = _activity_task_for_plan(plan_title, task_summary)
        set_busy(state.get("chat_id") or "", task=activity_task, worker_id=out.get("assigned_worker_id", assigned))

        # Log del plan para PM2 / stdout: título + lista de tasks (worker en línea aparte)
        safe_title = (plan_title or "Sin título de plan").strip()
        if len(safe_title) > 80:
            safe_title = safe_title[:80] + "..."
        try:
            _tlist = list(tasks or [])[:8]
            tasks_preview = ", ".join(_tlist)
            if len(tasks or []) > 8:
                tasks_preview += ", …"
        except Exception:
            tasks_preview = ""
        if len(tasks_preview) > 200:
            tasks_preview = tasks_preview[:200] + "…"
        log_plan(
            _obs,
            '"%s" | tasks: [%s]',
            safe_title or "(vacío)",
            tasks_preview if tasks_preview else "(sin tareas)",
        )
        _assigned_for_log = (out.get("assigned_worker_id") or assigned or "").strip() or "?"
        log_sys(_obs, "Worker elegido para el plan: %s", _assigned_for_log)
        return out

    return plan_node
