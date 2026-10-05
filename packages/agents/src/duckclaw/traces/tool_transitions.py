"""Per-tool-call transitions (context -> action -> outcome) for an outcome predictor.

Conversation traces keep whole turns; a predictor that scores a tool call *before*
running it needs one row per call with an explicit outcome label. Each record holds:

- ``context``: the request being served and the calls already made this turn
  (name + status), i.e. what the agent knew when it chose the action;
- ``action``: tool name and arguments;
- ``outcome``: ``ok`` / ``error``, an ``error_kind`` and the head of the result.

Written next to the conversation traces (``tool_transitions/YYYY/MM/DD/transitions.jsonl``)
unless ``DUCKCLAW_TOOL_TRANSITIONS_DIR`` is set. Works on LangChain messages (live
capture) and on ChatML dicts (backfill from existing traces).
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Iterable

_LOCK = threading.Lock()
_ARGS_MAX = 2000
_CONTENT_HEAD = 1500
_REQUEST_MAX = 2000

# ponytail: regex labels over the tool result text; tools do not report a typed status.
# Upgrade path: have tools return {"status": ...} and read that first.
_ERROR_KINDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("sql_binder", re.compile(r"Binder Error", re.I)),
    ("sql_catalog", re.compile(r"Catalog Error", re.I)),
    ("sql_parser", re.compile(r"Parser Error", re.I)),
    ("unknown_tool", re.compile(r"^Herramienta desconocida|unknown tool", re.I)),
    ("blocked", re.compile(r"circuit|harness_precheck|bloquead|BLOCKED_", re.I)),
    ("timeout", re.compile(r"timed? ?out|timeout", re.I)),
    ("exception", re.compile(r"^Error:|Traceback \(most recent call last\)", re.I)),
)


def classify_tool_outcome(content: Any) -> tuple[str, str]:
    """``("ok", "")`` or ``("error", kind)`` from a tool result."""
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False, default=str)
    head = (text or "").strip()[:4000]
    for kind, pattern in _ERROR_KINDS:
        if pattern.search(head):
            return "error", kind
    if head.startswith("{"):
        try:
            data = json.loads(text)
        except (TypeError, ValueError):
            data = None
        if isinstance(data, dict) and (
            data.get("error")
            or str(data.get("status") or "").lower() in ("error", "failed")
            or data.get("ok") is False
        ):
            return "error", "tool_error_json"
    return "ok", ""


def _get(msg: Any, key: str) -> Any:
    return msg.get(key) if isinstance(msg, dict) else getattr(msg, key, None)


def _role(msg: Any) -> str:
    if isinstance(msg, dict):
        return str(msg.get("role") or "")
    return {"human": "user", "ai": "assistant", "tool": "tool", "system": "system"}.get(
        str(getattr(msg, "type", "") or ""), ""
    )


def _calls(msg: Any) -> list[tuple[str, Any, str]]:
    """(name, args, id) for an assistant message, LangChain or ChatML shape."""
    out = []
    for tc in _get(msg, "tool_calls") or []:
        fn = tc.get("function") if isinstance(tc, dict) else None
        if isinstance(fn, dict):  # ChatML: {"function": {"name", "arguments": "<json>"}}
            args: Any = fn.get("arguments")
            try:
                args = json.loads(args) if isinstance(args, str) else args
            except ValueError:
                pass
            out.append((str(fn.get("name") or ""), args, str(tc.get("id") or "")))
        else:
            out.append((str(tc.get("name") or ""), tc.get("args"), str(tc.get("id") or "")))
    return out


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(p.get("text") or "") if isinstance(p, dict) else str(p) for p in content)
    return str(content or "")


def build_transitions(
    messages: Iterable[Any],
    *,
    session_id: str = "",
    worker_id: str = "",
    tenant_id: str = "",
    timestamp: str = "",
) -> list[dict[str, Any]]:
    """One record per (assistant tool call -> matching tool result) in ``messages``."""
    msgs = list(messages)
    records: list[dict[str, Any]] = []
    request = ""
    done: list[dict[str, str]] = []  # calls already made for the current request
    pending: dict[str, tuple[str, Any]] = {}
    queue: list[tuple[str, Any]] = []  # ChatML results may lack tool_call_id: match in order
    for msg in msgs:
        role = _role(msg)
        if role == "user":
            request, done, pending, queue = _text(_get(msg, "content"))[:_REQUEST_MAX], [], {}, []
        elif role == "assistant":
            for name, args, cid in _calls(msg):
                call = (name, args)  # same object in both: matched by id or by order
                pending[cid] = call
                queue.append(call)
        elif role == "tool":
            cid = str(_get(msg, "tool_call_id") or "")
            name = str(_get(msg, "name") or "")
            if cid and cid in pending:
                call = pending.pop(cid)
                queue = [q for q in queue if q is not call]
            else:
                idx = next((i for i, q in enumerate(queue) if q[0] == name), 0 if queue else None)
                if idx is None:
                    continue
                call = queue.pop(idx)
                pending = {k: v for k, v in pending.items() if v is not call}
            content = _text(_get(msg, "content"))
            status, kind = classify_tool_outcome(content)
            args_json = json.dumps(call[1], ensure_ascii=False, default=str)
            records.append(
                {
                    "ts": timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "session_id": session_id[:128],
                    "worker_id": worker_id[:64],
                    "tenant_id": tenant_id[:64],
                    "context": {"request": request, "prior_calls": list(done)},
                    "action": {"tool": call[0] or name, "args": args_json[:_ARGS_MAX]},
                    "outcome": {
                        "status": status,
                        "error_kind": kind,
                        "content_len": len(content),
                        "content_head": content[:_CONTENT_HEAD],
                    },
                }
            )
            done.append({"tool": call[0] or name, "status": status})
    return records


def record_tool_round(messages: list[Any], n_before: int, *, state: dict[str, Any], worker_id: str) -> None:
    """Capture the tool calls answered in this tools_node round (live graph hook).

    Builds over the whole turn so ``prior_calls`` include earlier rounds, then keeps
    only the records for the tool results appended after ``n_before``.
    """
    try:
        k = sum(1 for m in messages[n_before:] if _role(m) == "tool")
        if not k:
            return
        records = build_transitions(
            messages,
            session_id=str(state.get("chat_id") or state.get("session_id") or ""),
            worker_id=str(worker_id or ""),
            tenant_id=str(state.get("tenant_id") or ""),
        )
        append_tool_transitions(records[-k:])
    except Exception:  # noqa: BLE001 - telemetry must never break a turn
        pass


def tool_transitions_dir() -> Path:
    env = os.environ.get("DUCKCLAW_TOOL_TRANSITIONS_DIR", "").strip()
    if env:
        return Path(env).resolve()
    from duckclaw.graphs.conversation_traces import get_conversation_traces_dir

    return get_conversation_traces_dir().parent / "tool_transitions"


def append_tool_transitions(records: list[dict[str, Any]]) -> None:
    """Best-effort JSONL append (never raises into the agent turn)."""
    if not records:
        return
    if os.environ.get("DUCKCLAW_SAVE_TOOL_TRANSITIONS", "true").strip().lower() not in ("true", "1", "yes"):
        return
    now = time.gmtime()
    path = tool_transitions_dir() / str(now.tm_year) / f"{now.tm_mon:02d}" / f"{now.tm_mday:02d}" / "transitions.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = "".join(json.dumps(r, ensure_ascii=False, default=str) + "\n" for r in records)
        with _LOCK, path.open("a", encoding="utf-8") as fh:
            fh.write(lines)
    except OSError:
        pass
