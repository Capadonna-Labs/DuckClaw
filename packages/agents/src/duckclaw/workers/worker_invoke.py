"""Shared worker graph invoke for manager delegation and allowed_delegates."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger(__name__)
_obs = None

_delegate_depth: ContextVar[int] = ContextVar("duckclaw_worker_delegate_depth", default=0)
_parent_vault_lock: ContextVar[threading.RLock | None] = ContextVar(
    "duckclaw_parent_vault_invoke_lock",
    default=None,
)
_MAX_DELEGATE_DEPTH = 1
_DELEGATE_INVOKE_TIMEOUT_SEC = max(
    60.0,
    float(os.environ.get("DUCKCLAW_DELEGATE_INVOKE_TIMEOUT_SEC") or "900"),
)


def set_parent_vault_invoke_lock(lock: threading.RLock | None) -> None:
    """Manager holds per-vault lock for whole worker turn; nested delegate reads this."""
    _parent_vault_lock.set(lock)


def get_parent_vault_invoke_lock() -> threading.RLock | None:
    return _parent_vault_lock.get()


def _obs_logger():
    global _obs
    if _obs is None:
        from duckclaw.utils.logger import get_obs_logger

        _obs = get_obs_logger()
    return _obs


@dataclass(frozen=True)
class WorkerInvokeResult:
    status: str
    reply: str
    raw_reply: str
    elapsed_ms: int
    delegate_worker_id: str
    report_id: str | None = None
    worker_invoke: dict[str, Any] | None = None
    messages: Any = None
    error: str | None = None


def _normalize_delegate_id(worker_id: str, templates_root: Path | None) -> str:
    from duckclaw.workers.template_registry import resolve_template_id_global

    wid = (worker_id or "").strip()
    return resolve_template_id_global(wid, templates_root) or wid


def _is_target_allowed(
    caller_spec: Any,
    target_worker_id: str,
    templates_root: Path | None,
) -> bool:
    allowed = tuple(getattr(caller_spec, "allowed_delegates", None) or ())
    if not allowed:
        return False
    target = _normalize_delegate_id(target_worker_id, templates_root)
    normalized_allowed = {_normalize_delegate_id(w, templates_root) for w in allowed}
    return target in normalized_allowed


def _extract_report_id_from_messages(messages: Any) -> str | None:
    if not isinstance(messages, (list, tuple)):
        return None
    for msg in reversed(messages):
        name = getattr(msg, "name", None)
        if name is None and isinstance(msg, dict):
            name = msg.get("name")
        if name != "publish_custom_report":
            continue
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")
        if not content:
            continue
        try:
            parsed = json.loads(content) if isinstance(content, str) else content
            if isinstance(parsed, dict) and parsed.get("status") == "success":
                rid = str(parsed.get("report_id") or "").strip()
                if rid:
                    return rid
        except Exception:
            continue
    return None


def invoke_worker_graph(
    worker_graph: Any,
    worker_state: dict[str, Any],
    *,
    trace_cfg: Any = None,
    chat_id: str = "",
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    from duckclaw.graphs.chat_cancel import raise_if_chat_cancelled

    raise_if_chat_cancelled(str(chat_id or "").strip())

    def _run() -> dict[str, Any]:
        if trace_cfg is not None:
            return worker_graph.invoke(worker_state, trace_cfg)
        return worker_graph.invoke(worker_state)

    limit = timeout_sec if timeout_sec is not None else _DELEGATE_INVOKE_TIMEOUT_SEC
    if limit <= 0:
        return _run()
    # ponytail: orphan thread may keep running after timeout; upgrade = cancel token in graph
    # contextvars don't cross ThreadPoolExecutor.submit() on their own (unlike asyncio tasks) —
    # copy the caller's context explicitly so _parent_vault_lock/_delegate_depth reach the pool
    # thread. Without this, a delegate targeting the same vault as its caller deadlocks: the
    # pool thread can't see the RLock its ancestor already holds, tries to re-acquire it, and
    # blocks forever (an RLock is only reentrant for the thread that owns it).
    ctx = contextvars.copy_context()
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="delegate-invoke") as pool:
        fut = pool.submit(ctx.run, _run)
        try:
            return fut.result(timeout=limit)
        except FuturesTimeoutError as exc:
            raise TimeoutError(
                f"delegate worker graph exceeded {limit:.0f}s (chat_id={chat_id or '?'})"
            ) from exc


def extract_worker_invoke_reply(worker_invoke: dict[str, Any]) -> str:
    return str(
        worker_invoke.get("internal_reply")
        or worker_invoke.get("reply")
        or worker_invoke.get("output")
        or "Sin respuesta."
    )


def invoke_delegated_worker(
    *,
    caller_worker_id: str,
    caller_spec: Any,
    target_worker_id: str,
    task: str,
    state: dict[str, Any],
    db: Any,
    llm: Any,
    templates_root: Path | None,
    tenant_id: str,
    vault_db_path: str = "",
    shared_db_path: str = "",
    llm_provider: str = "",
    llm_model: str = "",
    llm_base_url: str = "",
) -> WorkerInvokeResult:
    from duckclaw.commands.history import append_task_audit
    from duckclaw.manager import manager_worker_cache as worker_cache_mod
    from duckclaw.manager.manager_invoke_helpers import (
        build_worker_cache_key,
        prepare_worker_invoke_state,
    )
    from duckclaw.utils.logger import log_sys
    from duckclaw.workers.factory import build_worker_graph as _build_worker_graph

    caller = (caller_worker_id or "").strip()
    target = _normalize_delegate_id(target_worker_id, templates_root)
    task_s = (task or "").strip()
    tenant_s = str(tenant_id or "default").strip() or "default"
    chat_id = str(state.get("chat_id") or state.get("session_id") or "").strip()
    user_id = str(state.get("user_id") or chat_id or "default").strip()
    history = state.get("history") or []
    t0 = time.monotonic()
    status = "SUCCESS"
    vault_lock_obj: threading.Lock | None = None
    lock_owned_by_ancestor = False

    if _delegate_depth.get() >= _MAX_DELEGATE_DEPTH:
        return WorkerInvokeResult(
            status="error",
            reply="Delegación anidada no permitida (máximo 1 nivel).",
            raw_reply="",
            elapsed_ms=0,
            delegate_worker_id=target,
            error="depth_exceeded",
        )

    if not _is_target_allowed(caller_spec, target, templates_root):
        return WorkerInvokeResult(
            status="error",
            reply=f"Worker {target!r} no está en allowed_delegates del caller.",
            raw_reply="",
            elapsed_ms=0,
            delegate_worker_id=target,
            error="not_allowed",
        )

    if not task_s:
        return WorkerInvokeResult(
            status="error",
            reply="task requerido para invoke_worker.",
            raw_reply="",
            elapsed_ms=0,
            delegate_worker_id=target,
            error="missing_task",
        )

    if chat_id and "report_id" not in task_s.lower():
        task_s = f"report_id={chat_id}. {task_s}"

    depth_prev = _delegate_depth.get()
    _delegate_depth.set(depth_prev + 1)
    try:
        try:
            from duckclaw.vaults import resolve_template_vault_path
            from duckclaw.workers.manifest import load_manifest

            spec_target = load_manifest(target, templates_root, db=db, tenant_id=tenant_s)
            tpl_vault = resolve_template_vault_path(spec_target.forge_vault_binding, user_id)
            if tpl_vault:
                vault_db_path = tpl_vault
        except Exception:
            spec_target = None

        worker_resolved = ""
        try:
            from duckclaw.workers.factory import _get_db_path

            worker_resolved = _get_db_path(
                target, tenant_s, (vault_db_path or None)
            ).strip()
        except Exception:
            pass

        _vk = worker_cache_mod._vault_lock_key(worker_resolved)
        parent_lock = get_parent_vault_invoke_lock()
        if _vk:
            vault_lock_obj = worker_cache_mod.get_vault_invoke_lock(worker_resolved)
            # Delegate targets the same vault an ancestor call already locked (any caller/target
            # pair whose manifests share a vault_id). Re-acquiring here would deadlock once
            # invoke_worker_graph's context propagation makes the ancestor's lock visible on
            # this (pool) thread: an RLock is only reentrant for the thread that owns it, and the
            # ancestor is blocked on this call's result, so it can never release first. The
            # ancestor's held lock already serializes access for the whole nested call chain, so
            # skip acquiring — and skip releasing in `finally` too, since we never took it.
            lock_owned_by_ancestor = vault_lock_obj is not None and parent_lock is vault_lock_obj
            if vault_lock_obj is not None and not lock_owned_by_ancestor:
                vault_lock_obj.acquire()

        try:
            from duckclaw.forge.skills.report_engine_hub_context import set_report_engine_hub_db

            set_report_engine_hub_db(db)
        except Exception:
            pass

        worker_cache_key = build_worker_cache_key(
            tenant_id=tenant_s,
            assigned=target,
            vault_db_path=vault_db_path or worker_resolved,
            db_path=worker_resolved,
            shared_db_path=shared_db_path,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            combined=task_s,
            visual_lite_mcp=False,
            lite_stdio_mcp=False,
            url_research_mcp=False,
            summarize_vault_ro=False,
            vis_prov="local",
        )
        worker_graph = worker_cache_mod.worker_graph_cache_get(worker_cache_key)
        if worker_graph is None:
            worker_graph = _build_worker_graph(
                target,
                vault_db_path or None,
                llm,
                templates_root=templates_root,
                llm_provider=llm_provider or "",
                llm_model=llm_model or "",
                llm_base_url=llm_base_url or "",
                instance_name=tenant_s,
                shared_db_path=shared_db_path or None,
                reuse_db=db,
                db=db,
                tenant_id=tenant_s,
                tool_surface="full",
                incoming_hint=task_s,
            )
            worker_cache_mod.remember_worker_graph_cache(worker_cache_key, worker_graph)

        agent_label = f"{caller}->{target}".strip()
        worker_state = prepare_worker_invoke_state(
            state=state,
            planned_task_for_worker=task_s,
            incoming=task_s,
            history=history if isinstance(history, list) else [],
            chat_id=chat_id,
            tenant_id=tenant_s,
            user_id=user_id,
            vault_db_path=vault_db_path,
            shared_db_path=shared_db_path,
            agent_instance_label=agent_label,
            plan_title=f"delegate:{caller}",
            pa=0,
            max_a=1,
            assigned=target,
        )
        worker_state["suppress_subagent_egress"] = True

        worker_invoke = invoke_worker_graph(worker_graph, worker_state, chat_id=chat_id)
        raw_reply = extract_worker_invoke_reply(worker_invoke)
        messages = worker_invoke.get("messages")
        if isinstance(messages, tuple):
            messages = list(messages)
        report_id = _extract_report_id_from_messages(messages) or chat_id or None
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        log_sys(
            _obs_logger(),
            "worker_delegate caller=%s target=%s status=%s elapsed_ms=%d report_id=%s",
            caller,
            target,
            status,
            elapsed_ms,
            report_id or "",
        )
        try:
            append_task_audit(
                db,
                tenant_s,
                target,
                query_prefix=f"delegate_from:{caller}",
                status=status,
                duration_ms=elapsed_ms,
                plan_title=f"delegate:{caller}",
            )
        except Exception:
            _log.debug("append_task_audit delegate failed", exc_info=True)

        return WorkerInvokeResult(
            status="success",
            reply=raw_reply,
            raw_reply=raw_reply,
            elapsed_ms=elapsed_ms,
            delegate_worker_id=target,
            report_id=report_id,
            worker_invoke=worker_invoke if isinstance(worker_invoke, dict) else None,
            messages=messages,
        )
    except Exception as exc:
        status = "ERROR"
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        msg = str(exc)[:2048]
        log_sys(
            _obs_logger(),
            "worker_delegate caller=%s target=%s status=%s elapsed_ms=%d report_id=%s",
            caller,
            target,
            status,
            elapsed_ms,
            "",
        )
        try:
            append_task_audit(
                db,
                tenant_s,
                target,
                query_prefix=f"delegate_from:{caller}",
                status=status,
                duration_ms=elapsed_ms,
                plan_title=f"delegate:{caller}",
            )
        except Exception:
            pass
        return WorkerInvokeResult(
            status="error",
            reply=msg or "Error al invocar worker delegado.",
            raw_reply="",
            elapsed_ms=elapsed_ms,
            delegate_worker_id=target,
            error=msg,
        )
    finally:
        _delegate_depth.set(depth_prev)
        if vault_lock_obj is not None and not lock_owned_by_ancestor:
            try:
                vault_lock_obj.release()
            except Exception:
                pass
        try:
            from duckclaw.forge.skills.report_engine_hub_context import clear_report_engine_hub_db

            clear_report_engine_hub_db()
        except Exception:
            pass


__all__ = [
    "WorkerInvokeResult",
    "extract_worker_invoke_reply",
    "get_parent_vault_invoke_lock",
    "invoke_delegated_worker",
    "invoke_worker_graph",
    "set_parent_vault_invoke_lock",
]
