"""tools_node for worker LangGraph."""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.utils.logger import format_chat_log_identity, set_log_context
from duckclaw.workers.db_runtime import RUN_SANDBOX_TOOL_LLM_MAX_CHARS as _RUN_SANDBOX_TOOL_LLM_MAX_CHARS
from duckclaw.workers.factory_agent_node_helpers import (
    _identity_fields,
    _raise_if_chat_cancelled_from_state,
    _worker_log_label,
)
from duckclaw.workers.factory_graph_context import WorkerGraphContext
from duckclaw.workers.factory_sandbox_notify import (
    _heartbeat_elapsed_sec,
    _sandbox_heartbeat_allowed,
    _schedule_run_browser_novnc_tool_heartbeat,
    _send_sandbox_heartbeat_telegram,
)
from duckclaw.workers.skill_tool_registry import read_visual_artifact_image_as_b64 as _read_visual_artifact_image_as_b64
from duckclaw.workers.tool_output_truncation import compact_run_sandbox_tool_content_for_llm as _compact_run_sandbox_tool_content_for_llm
from langchain_core.messages import ToolMessage

_log = logging.getLogger(__name__)


def make_tools_node(ctx: WorkerGraphContext):

    worker_id = ctx.worker_id
    db = ctx.db
    spec = ctx.spec
    path = ctx.path
    shared_resolved = ctx.shared_resolved
    tools_by_name = ctx.tools_by_name
    tools_by_name_sandbox_off = ctx.tools_by_name_sandbox_off
    use_cm = ctx.use_context_monitor
    _sandbox_enabled_for_state = ctx.sandbox_enabled_for_state
    from duckclaw.workers import read_pool

    def tools_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        _cid_tools = str(state.get("chat_id") or state.get("session_id") or "").strip()
        _raise_if_chat_cancelled_from_state(state)
        from duckclaw.graphs.chat_heartbeat import (
            format_tool_heartbeat,
            heartbeat_message_for_tool,
            schedule_chat_heartbeat_dm,
        )
        from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable

        _chat_ctx = state.get("chat_id") or state.get("session_id") or "default"
        _tenant_ctx = (state.get("tenant_id") or "").strip() or "default"
        _log_chat = format_chat_log_identity(str(_chat_ctx).strip() or "default", state.get("username"))
        set_log_context(tenant_id=_tenant_ctx, worker_id=worker_id, chat_id=_log_chat)
        _wl = _worker_log_label(worker_id)
        messages = state["messages"]
        last = messages[-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        _tool_round = int(state.get("_tool_round") or 0) + 1
        new_msgs = list(messages)
        sandbox_enabled = _sandbox_enabled_for_state(state)
        tool_lookup = tools_by_name if sandbox_enabled else tools_by_name_sandbox_off
        sandbox_b64: str | None = state.get("sandbox_photo_base64") if isinstance(state.get("sandbox_photo_base64"), str) else None
        visual_artifact_id: str | None = (
            str(state.get("visual_artifact_id") or "").strip() or None
        )
        _hb_head = (state.get("subagent_instance_label") or "").strip() or None
        _hb_uname = (state.get("username") or "").strip() or None
        _hb_plan = (state.get("heartbeat_plan_title") or "").strip() or None
        _hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None

        _duck_exts = list(getattr(spec, "duckdb_extensions", None) or [])
        # DuckDB mismo PID: sesión principal RW (read_only=False) + connect RO efímero al mismo archivo →
        # "different configuration than existing". Workers RO pueden desactivar pool vía manifest
        # por contención con db-writer.
        use_ephemeral_parallel = (
            read_pool.read_pool_active_for_worker(spec)
            and read_pool.should_parallelize_ephemeral_tool_calls(tool_calls)
            and bool(getattr(spec, "read_only", False))
        )

        def _notify_admin_tool_phase(
            tool_name: str,
            phase: str,
            detail: str = "",
            *,
            elapsed_ms: float | None = None,
        ) -> None:
            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
            if not _hcid:
                return
            try:
                from duckclaw.graphs.chat_heartbeat import (
                    is_admin_ui_chat_session,
                    publish_admin_tool_event,
                )

                if not is_admin_ui_chat_session(_hcid):
                    return
                publish_admin_tool_event(
                    _hcid,
                    tool_name,
                    phase,
                    worker_id=(_hb_head or worker_id or "").strip() or None,
                    detail=detail,
                    elapsed_ms=elapsed_ms,
                )
            except Exception:
                pass

        def _schedule_tool_heartbeat(tool_name: str) -> None:
            _htid = (state.get("tenant_id") or "default").strip() or "default"
            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
            _huid = str(state.get("user_id") or "").strip() or _hcid
            try:
                from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

                _admin_ui = is_admin_ui_chat_session(_hcid)
            except Exception:
                _admin_ui = False
            if _admin_ui:
                _notify_admin_tool_phase(tool_name, "start")
                return
            _elapsed = _heartbeat_elapsed_sec(state)
            schedule_chat_heartbeat_dm(
                _htid,
                _hcid,
                _huid,
                format_tool_heartbeat(
                    _hb_head,
                    heartbeat_message_for_tool(tool_name),
                    plan_title=_hb_plan,
                    elapsed_sec=_elapsed,
                ),
                log_worker_id=_hb_head,
                log_username=_hb_uname,
                log_plan_title=_hb_plan,
                outbound_bot_token=_hb_tok,
                routing_worker_id=worker_id,
            )

        if use_ephemeral_parallel:
            _log.info("[%s] tools_node: ephemeral read-pool parallel (%d calls)", _wl, len(tool_calls))
            n_workers = min(len(tool_calls), read_pool.read_pool_max_concurrency())

            def _parallel_job(idx_tc: tuple[int, dict[str, Any]]) -> tuple[int, str, str, str]:
                idx, tc = idx_tc
                name = (tc.get("name") or "").strip()
                args = tc.get("args") or {}
                tid = tc.get("id") or ""
                _schedule_tool_heartbeat(name)
                _tool_t0 = time.perf_counter()
                try:
                    if name == "read_sql":
                        q = str(args.get("query", "")) if isinstance(args, dict) else ""
                        content = read_pool.run_ephemeral_read_sql(
                            spec, path, path, shared_resolved, _duck_exts, q
                        )
                    elif name == "inspect_schema":
                        content = read_pool.run_ephemeral_inspect_schema(
                            path, path, shared_resolved, _duck_exts
                        )
                    else:
                        content = json.dumps({"error": f"Herramienta inesperada en read-pool: {name}"})
                except Exception as e:
                    content = f"Error: {e}"
                    _log.warning("[%s] ephemeral tool=%s failed: %s", _wl, name, e)
                    _notify_admin_tool_phase(
                        name,
                        "error",
                        str(e)[:240],
                        elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                    )
                else:
                    _notify_admin_tool_phase(
                        name,
                        "done",
                        "",
                        elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                    )
                _log.info(
                    "[%s] tool=%s | ephemeral | result_len=%d | preview=%r",
                    _wl,
                    name,
                    len(content),
                    content[:120] + ("..." if len(content) > 120 else ""),
                )
                return idx, tid, name, content

            ordered_slots: list[tuple[str, str, str] | None] = [None] * len(tool_calls)
            with ThreadPoolExecutor(max_workers=max(1, n_workers)) as pool:
                futs = [pool.submit(_parallel_job, (i, tc)) for i, tc in enumerate(tool_calls)]
                for fut in as_completed(futs):
                    idx, tid, name, content = fut.result()
                    ordered_slots[idx] = (tid, name, content)
            for i in range(len(tool_calls)):
                slot = ordered_slots[i]
                if slot is None:
                    tc = tool_calls[i]
                    new_msgs.append(
                        ToolMessage(
                            content=json.dumps({"error": "read_pool: resultado faltante"}),
                            tool_call_id=tc.get("id") or "",
                            name=(tc.get("name") or "").strip(),
                        )
                    )
                    continue
                tid, name, content = slot
                new_msgs.append(ToolMessage(content=content, tool_call_id=tid, name=name))
        else:
            for tc in tool_calls:
                _raise_if_chat_cancelled_from_state(state)
                name = (tc.get("name") or "").strip()
                args = tc.get("args") or {}
                tid = tc.get("id") or ""
                tool = tool_lookup.get(name)
                if tool:
                    _tool_t0: float | None = None
                    try:
                        invoke_args: Any = args
                        if isinstance(args, dict):
                            invoke_args = {**args}
                        if name in (
                            "run_sandbox",
                            "run_browser_sandbox",
                            "execute_sandbox_script",
                        ):
                            if not str(invoke_args.get("worker_id") or "").strip():
                                invoke_args["worker_id"] = worker_id
                            _cid_sb = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if _cid_sb and not str(invoke_args.get("chat_id") or "").strip():
                                invoke_args["chat_id"] = _cid_sb
                            if _cid_sb and not str(invoke_args.get("session_id") or "").strip():
                                from duckclaw.graphs.novnc_registry import sanitize_chat_to_session_id

                                invoke_args["session_id"] = sanitize_chat_to_session_id(_cid_sb)
                        if name == "get_browser_session_url":
                            if not isinstance(invoke_args, dict):
                                invoke_args = {}
                            _cid = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if _cid and not str(invoke_args.get("chat_id") or "").strip():
                                invoke_args["chat_id"] = _cid
                        if name == "run_browser_sandbox":
                            from duckclaw.graphs.sandbox import ensure_browser_novnc_session

                            _sid = str(invoke_args.get("session_id") or "").strip()
                            _cid_sb = str(invoke_args.get("chat_id") or state.get("chat_id") or "").strip()
                            _vnc_pre = (
                                ensure_browser_novnc_session(
                                    worker_id,
                                    _sid,
                                    db=db,
                                    chat_id=_cid_sb or None,
                                )
                                if _sid
                                else None
                            )
                            _schedule_run_browser_novnc_tool_heartbeat(
                                state,
                                routing_worker_id=worker_id,
                                vnc_url=_vnc_pre,
                                novnc_session_id=_sid or "",
                            )
                        _schedule_tool_heartbeat(name)
                        if (
                            name == "run_sandbox"
                            and _sandbox_heartbeat_allowed(spec)
                        ):
                            from duckclaw.graphs.chat_heartbeat import is_chat_heartbeat_enabled

                            _htid = (state.get("tenant_id") or "default").strip() or "default"
                            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if not is_chat_heartbeat_enabled(_htid, _hcid):
                                _send_sandbox_heartbeat_telegram(state)
                        _tool_t0 = time.perf_counter()
                        result = tool.invoke(invoke_args)
                        content = str(result) if result is not None else "OK"
                        if name in ("run_sandbox", "run_browser_sandbox"):
                            try:
                                payload = json.loads(content)
                                if isinstance(payload, dict) and payload.get("exit_code") == 0:
                                    fb = payload.get("figure_base64")
                                    if isinstance(fb, str) and len(fb) > 32:
                                        sandbox_b64 = fb
                            except (json.JSONDecodeError, TypeError):
                                pass
                        if name in ("generate_visual_asset", "edit_visual_asset"):
                            try:
                                payload = json.loads(content)
                                if isinstance(payload, dict) and payload.get("ok"):
                                    aid = str(payload.get("artifact_id") or "").strip()
                                    if aid:
                                        visual_artifact_id = aid
                                        try:
                                            from duckclaw.graphs.chat_heartbeat import (
                                                is_admin_ui_chat_session,
                                                publish_admin_chat_heartbeat,
                                            )

                                            _cid = str(state.get("chat_id") or "").strip()
                                            if _cid and is_admin_ui_chat_session(_cid):
                                                publish_admin_chat_heartbeat(
                                                    _cid,
                                                    "Imagen generada (ComfyUI)",
                                                    kind="visual",
                                                    artifact_id=aid,
                                                    artifact_tenant_id=_tenant_ctx,
                                                )
                                        except Exception:
                                            pass
                                    fb = payload.get("figure_base64")
                                    if isinstance(fb, str) and len(fb) > 32:
                                        sandbox_b64 = fb
                                    elif payload.get("artifacts"):
                                        arts = payload.get("artifacts")
                                        if isinstance(arts, list) and arts:
                                            first = str(arts[0] or "").strip()
                                            if first:
                                                b64_art = _read_visual_artifact_image_as_b64(
                                                    first,
                                                    _tenant_ctx,
                                                )
                                                if b64_art:
                                                    sandbox_b64 = b64_art
                            except (json.JSONDecodeError, TypeError):
                                pass
                            if not use_cm:
                                content = _compact_run_sandbox_tool_content_for_llm(
                                    content, _RUN_SANDBOX_TOOL_LLM_MAX_CHARS
                                )
                        if name.startswith("reddit_"):
                            content = format_reddit_mcp_reply_if_applicable(content)
                        _prev = content[:120] + ("..." if len(content) > 120 else "")
                        _log.info(
                            "[%s] tool=%s | result_len=%d | preview=%r",
                            _wl,
                            name,
                            len(content),
                            _prev,
                        )
                        _admin_detail = _prev
                        if name in ("read_sql", "admin_sql", "inspect_schema", "get_schema_info"):
                            _admin_detail = ""
                        elif name == "run_browser_sandbox":
                            try:
                                _bp = json.loads(content)
                                if isinstance(_bp, dict) and _bp.get("browser_image_missing"):
                                    _admin_detail = str(_bp.get("hint") or _admin_detail)[:240]
                            except (json.JSONDecodeError, TypeError):
                                pass
                        _notify_admin_tool_phase(
                            name,
                            "done",
                            _admin_detail,
                            elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                        )
                    except Exception as e:
                        content = f"Error: {e}"
                        _log.warning("[%s] tool=%s failed: %s", _wl, name, e)
                        _notify_admin_tool_phase(
                            name,
                            "error",
                            str(e)[:240],
                            elapsed_ms=(
                                (time.perf_counter() - _tool_t0) * 1000 if _tool_t0 is not None else None
                            ),
                        )
                else:
                    if not sandbox_enabled and name in (
                        "run_sandbox",
                        "run_browser_sandbox",
                        "get_browser_session_url",
                    ):
                        content = "Sandbox deshabilitado en esta sesión. Actívalo con /sandbox on."
                    else:
                        content = f"Herramienta desconocida: {name}"
                    _log.warning(
                        "[%s] unknown/unavailable tool: %s (sandbox_enabled=%s)",
                        _wl,
                        name,
                        sandbox_enabled,
                    )
                new_msgs.append(ToolMessage(content=content, tool_call_id=tid, name=name))
        out: dict[str, Any] = {**state, "messages": new_msgs, "_tool_round": _tool_round}
        if sandbox_b64:
            out["sandbox_photo_base64"] = sandbox_b64
        if visual_artifact_id:
            out["visual_artifact_id"] = visual_artifact_id
        out.update(_identity_fields(state))
        return out

    return tools_node