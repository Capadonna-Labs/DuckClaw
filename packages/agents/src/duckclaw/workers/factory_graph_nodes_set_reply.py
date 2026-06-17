"""set_reply node for worker LangGraph."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.egress.tool_response_repair import (
    deterministic_tool_response_summary as _deterministic_tool_response_summary,
    repair_tool_response_egress_reply as _repair_tool_response_egress_reply,
    reply_is_tool_json_echo as _reply_is_tool_json_echo,
    tool_response_needs_egress_repair as _tool_response_needs_egress_repair,
)
from duckclaw.workers.factory_agent_node_helpers import (
    _identity_fields,
    _last_human_message_index,
    _spec_logical_worker_id,
)
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_set_reply_tool_cap import maybe_reply_for_tool_cap_exhausted
from duckclaw.workers.factory_sandbox_notify import _heartbeat_elapsed_sec
from duckclaw.workers.visual_evidence_policy import visual_evidence_max_retries as _visual_evidence_max_retries

_log = logging.getLogger(__name__)


def make_set_reply_node(ctx: WorkerGraphContext):

    worker_id = ctx.worker_id
    db = ctx.db
    spec = ctx.spec
    llm = ctx.llm
    tool_surface = ctx.tool_surface
    is_market_analysis_worker = ctx.is_market_analysis_worker
    tools_by_name = ctx.tools_by_name
    tools_by_name_sandbox_off = ctx.tools_by_name_sandbox_off
    use_cm = ctx.use_context_monitor
    _sandbox_enabled_for_state = ctx.sandbox_enabled_for_state
    from duckclaw.integrations.llm_providers import extract_embedded_tool_invokes

    def set_reply(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.workers.reddit_formatters import format_reddit_mcp_reply_if_applicable
        from duckclaw.utils import format_tool_reply
        from duckclaw.egress.user_reply_nl_synthesis import (
            incoming_has_context_summarize_directive,
            maybe_synthesize_reply,
            repair_summarize_new_context_egress,
            replace_bare_summarize_image_on_vlm_gateway_down,
            replace_bare_wrong_summarize_stored_echo,
            rescind_trivial_context_summary_reply,
            state_evidence_for_context_summary_rescind,
        )
        from duckclaw.graphs.chat_heartbeat import format_tool_heartbeat, schedule_chat_heartbeat_dm
        from duckclaw.integrations.llm_providers import (
            lc_message_content_to_text,
            sanitize_worker_reply_phase1,
            sanitize_worker_reply_text,
        )
        from langchain_core.messages import ToolMessage

        def _notify_final_heartbeat() -> None:
            from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

            _cid_hb = str(state.get("chat_id") or state.get("session_id") or "").strip()
            if is_admin_ui_chat_session(_cid_hb):
                return
            _tid = (state.get("tenant_id") or "default").strip() or "default"
            _cid = _cid_hb
            _uid = str(state.get("user_id") or "").strip() or _cid
            _head = (state.get("subagent_instance_label") or "").strip() or None
            _un = (state.get("username") or "").strip() or None
            _pt = (state.get("heartbeat_plan_title") or "").strip() or None
            _elapsed = _heartbeat_elapsed_sec(state)
            _tok_f = (state.get("outbound_telegram_bot_token") or "").strip() or None
            schedule_chat_heartbeat_dm(
                _tid,
                _cid,
                _uid,
                format_tool_heartbeat(
                    _head,
                    "✅ Terminé los pasos con herramientas; te resumo el resultado en el siguiente mensaje.",
                    plan_title=_pt,
                    elapsed_sec=_elapsed,
                ),
                log_worker_id=_head,
                log_username=_un,
                log_plan_title=_pt,
                outbound_bot_token=_tok_f,
                routing_worker_id=str(getattr(spec, "worker_id", "") or "").strip() or None,
            )

        msgs = state.get("messages") or []
        _inc_for_ctx = (state.get("incoming") or state.get("input") or "").strip()
        _cap_reply, _cap_msgs = maybe_reply_for_tool_cap_exhausted(
            state, ctx, list(msgs), _inc_for_ctx, spec
        )
        if _cap_reply is not None:
            msgs = _cap_msgs if _cap_msgs is not None else msgs
            reply = sanitize_worker_reply_text(_cap_reply)
            suppress_egress = bool(state.get("suppress_subagent_egress"))
            if suppress_egress:
                out = {**state, "reply": "", "internal_reply": reply, "messages": msgs}
            else:
                out = {**state, "reply": reply, "internal_reply": reply, "messages": msgs}
            out.update(_identity_fields(state))
            return out

        last = msgs[-1] if msgs else None
        reply = lc_message_content_to_text(last) if last else ""
        reply = sanitize_worker_reply_phase1(reply)
        reply = replace_bare_wrong_summarize_stored_echo(reply, incoming=_inc_for_ctx)
        reply = replace_bare_summarize_image_on_vlm_gateway_down(reply, incoming=_inc_for_ctx)
        reply = repair_summarize_new_context_egress(reply, incoming=_inc_for_ctx)
        reply = format_reddit_mcp_reply_if_applicable(reply)
        suppress_egress = bool(state.get("suppress_subagent_egress"))

        def _nl_user_ask() -> str:
            inc = state.get("incoming") or state.get("input") or ""
            return (inc.strip() if isinstance(inc, str) else str(inc or "")).strip()

        def _apply_nl_synthesis(candidate: str) -> str:
            return maybe_synthesize_reply(llm, spec=spec, user_ask=_nl_user_ask(), reply_candidate=candidate)

        if not msgs:
            out_empty = {**state, "reply": "Sin respuesta generada."}
            out_empty.update(_identity_fields(state))
            return out_empty
        _embedded_invokes = extract_embedded_tool_invokes(reply)
        if _embedded_invokes:
            from duckclaw.utils import format_tool_reply
            sandbox_enabled = _sandbox_enabled_for_state(state)
            tool_lookup = tools_by_name if sandbox_enabled else tools_by_name_sandbox_off
            for name, _params in _embedded_invokes:
                if name not in tool_lookup:
                    _log.warning(
                        "[%s] assistant JSON tool not in registry: %s (sandbox_tools=%s)",
                        getattr(spec, "worker_id", "?"),
                        name,
                        sandbox_enabled,
                    )
                    err = json.dumps(
                        {"error": f"Herramienta no disponible en este modo: {name}"},
                        ensure_ascii=False,
                    )
                    _eb = sanitize_worker_reply_text(_apply_nl_synthesis(format_tool_reply(err)))
                    out_bad = {**state, "reply": _eb, "messages": msgs}
                    out_bad.update(_identity_fields(state))
                    return out_bad
            try:
                _parts: list[str] = []
                for name, params in _embedded_invokes:
                    result = tool_lookup[name].invoke(params)
                    _parts.append(f"### {name}\n{format_tool_reply(result)}")
                _combined = "\n\n".join(_parts)
                _notify_final_heartbeat()
                _formatted = sanitize_worker_reply_text(
                    _apply_nl_synthesis(_combined)
                )
                out_tool = {**state, "reply": _formatted, "internal_reply": _formatted, "messages": msgs}
                out_tool.update(_identity_fields(state))
                return out_tool
            except Exception as e:
                _log.warning(
                    "[%s] JSON tool invoke failed (embedded multi/single): %s",
                    getattr(spec, "worker_id", "?"),
                    e,
                    exc_info=True,
                )
                err = json.dumps(
                    {
                        "error": str(e),
                        "hint": "Si el error menciona lock de DuckDB, cierra otras conexiones (CLI, IDE) a ese .duckdb.",
                    },
                    ensure_ascii=False,
                )
                _ee = sanitize_worker_reply_text(_apply_nl_synthesis(format_tool_reply(err)))
                out_err = {**state, "reply": _ee, "messages": msgs}
                out_err.update(_identity_fields(state))
                return out_err
        _visual_only_turn = bool(
            (state.get("sandbox_photo_base64") or "").strip()
            or (state.get("visual_artifact_id") or "").strip()
        )
        if _visual_only_turn and tool_surface == "visual_generation":
            _short = (reply or "").strip()
            if not _short or len(_short) > 240:
                _short = "Imagen generada."
            reply = _short
        else:
            _spec_lid = _spec_logical_worker_id(spec)
            _lh_repair = _last_human_message_index(list(msgs) if msgs else [])
            _egress_needs_repair = _tool_response_needs_egress_repair(
                list(msgs) if msgs else [],
                _inc_for_ctx,
                reply or "",
                last_human_idx=_lh_repair,
                repair_enabled=is_market_analysis_worker,
            )
            if _egress_needs_repair:
                _inline_synth_done = bool(state.get("market_inline_synthesis_attempted"))
                _skip_llm_synth = _inline_synth_done and bool((reply or "").strip())
                reply = _repair_tool_response_egress_reply(
                    llm,
                    spec,
                    _inc_for_ctx,
                    reply or "",
                    msgs,
                    skip_llm_synthesis=_skip_llm_synth,
                    worker_display_name=str(getattr(spec, "name", None) or ""),
                )
                if _reply_is_tool_json_echo(reply or ""):
                    _det_egress = _deterministic_tool_response_summary(
                        list(msgs),
                        _lh_repair,
                        _spec_lid,
                        _inc_for_ctx,
                        worker_display_name=str(getattr(spec, "name", None) or ""),
                    )
                    if _det_egress and not _reply_is_tool_json_echo(_det_egress):
                        reply = _det_egress
            reply = _apply_nl_synthesis(reply or "")
        _rescind_incoming = state_evidence_for_context_summary_rescind(state)
        reply = rescind_trivial_context_summary_reply(
            llm, spec, incoming=_rescind_incoming, reply_candidate=reply or ""
        )
        reply = format_reddit_mcp_reply_if_applicable(reply or "")
        if not suppress_egress:
            _notify_final_heartbeat()
        try:
            from duckclaw.egress.evidence_validator import (
                VISUAL_EVIDENCE_RETRY_REASON,
                enforce_visual_evidence_rule,
                market_price_consistency_audit,
                visual_evidence_retry_system_message,
            )

            # Turnos /context (SUMMARIZE_*): sin auditorías cuánticas/VLM que puedan sustituir el resumen.
            if reply and not incoming_has_context_summarize_directive(_rescind_incoming):
                new_v, vreason = enforce_visual_evidence_rule(
                    incoming=(state.get("incoming") or ""),
                    messages=msgs,
                    reply=reply,
                    db=db,
                    spec=spec,
                )
                if vreason == VISUAL_EVIDENCE_RETRY_REASON:
                    _ve_max = _visual_evidence_max_retries()
                    _ve_count = int(state.get("visual_evidence_retry_count") or 0)
                    if _ve_count < _ve_max:
                        _log.warning(
                            "Visual evidence audit: %s — in-graph retry %s/%s",
                            vreason,
                            _ve_count + 1,
                            _ve_max,
                        )
                        _msgs_retry = list(msgs) + [visual_evidence_retry_system_message()]
                        out_retry: dict = {
                            **state,
                            "messages": _msgs_retry,
                            "reply": "",
                            "internal_reply": "",
                            "visual_evidence_retry_count": _ve_count + 1,
                            "visual_evidence_graph_retry": True,
                        }
                        out_retry.update(_identity_fields(state))
                        _sb_retry = (state.get("sandbox_photo_base64") or "").strip()
                        if _sb_retry:
                            out_retry["sandbox_photo_base64"] = _sb_retry
                        _aid_retry = (state.get("visual_artifact_id") or "").strip()
                        if _aid_retry:
                            out_retry["visual_artifact_id"] = _aid_retry
                        return out_retry
                    _log.warning(
                        "Visual evidence audit: %s — retries exhausted",
                        vreason,
                    )
                    _spec_lid_ve = _spec_logical_worker_id(spec)
                    _lh_ve = _last_human_message_index(list(msgs) if msgs else [])
                    _det_ve = _deterministic_tool_response_summary(
                        list(msgs),
                        _lh_ve,
                        _spec_lid_ve,
                        _inc_for_ctx,
                        worker_display_name=str(getattr(spec, "name", None) or ""),
                    )
                    if _det_ve:
                        reply = sanitize_worker_reply_text(_det_ve)
                    elif is_market_analysis_worker and llm is not None:
                        _repaired = _repair_tool_response_egress_reply(
                            llm,
                            spec,
                            _inc_for_ctx,
                            "",
                            list(msgs),
                            skip_llm_synthesis=False,
                            worker_display_name=str(getattr(spec, "name", None) or ""),
                        )
                        if (_repaired or "").strip():
                            reply = sanitize_worker_reply_text(_repaired)
                    if not (reply or "").strip():
                        reply = (
                            "No pude validar las cifras de mercado de la imagen con datos del ledger. "
                            "Intenta de nuevo o especifica el símbolo."
                        )
                elif vreason:
                    _log.warning("Visual evidence audit: %s", vreason)
                    reply = new_v
                new_r, price_reason = market_price_consistency_audit(db, spec, reply, messages=msgs)
                if price_reason:
                    _log.warning("Market price audit: %s", price_reason)
                    reply = new_r
        except Exception:
            pass
        reply = sanitize_worker_reply_text(reply or "")
        if (not reply or reply.strip().lower() in ("sin respuesta.", "sin respuesta")) and msgs:
            _spec_lid_fb = _spec_logical_worker_id(spec)
            _lh_fb = _last_human_message_index(list(msgs))
            if (not reply or reply.strip().lower() in ("sin respuesta.", "sin respuesta")):
                _det = _deterministic_tool_response_summary(
                    list(msgs),
                    _lh_fb,
                    _spec_lid_fb,
                    _inc_for_ctx,
                    worker_display_name=str(getattr(spec, "name", None) or ""),
                )
                if _det:
                    reply = sanitize_worker_reply_text(_det)
                else:
                    for _m in reversed(msgs):
                        if isinstance(_m, ToolMessage):
                            _fallback = sanitize_worker_reply_text(format_tool_reply(_m.content))
                            if _fallback:
                                reply = _fallback
                                break
        try:
            from duckclaw.graphs.conversation_traces import sync_final_assistant_egress_in_langchain_messages

            sync_final_assistant_egress_in_langchain_messages(msgs, reply or "")
        except Exception:
            pass
        if suppress_egress:
            out = {**state, "reply": "", "internal_reply": (reply or ""), "messages": msgs}
        else:
            out = {**state, "reply": reply or "", "internal_reply": (reply or ""), "messages": msgs}
        sb = (state.get("sandbox_photo_base64") or "").strip()
        if sb:
            out["sandbox_photo_base64"] = sb
        aid = (state.get("visual_artifact_id") or "").strip()
        if aid:
            out["visual_artifact_id"] = aid
        out.update(_identity_fields(state))
        return out

    return set_reply
