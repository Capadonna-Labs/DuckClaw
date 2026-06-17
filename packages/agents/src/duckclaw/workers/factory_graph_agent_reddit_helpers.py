"""Reddit helpers extracted from agent node."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from duckclaw.workers.db_intent_policy import incoming_is_schema_query_heuristic
from duckclaw.workers.factory_reddit_helpers import (
    _extract_first_reddit_url,
    reddit_share_search_query_for_attempt,
)
from langchain_core.messages import ToolMessage

def incoming_has_reddit_url(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    return bool(re.search(r"(?:reddit\.com|redd\.it)/", str(text), re.IGNORECASE))

def incoming_looks_like_reddit_post_url(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    return bool(
        re.search(
            r"(?:https?://)?(?:www\.)?reddit\.com/r/[\w_]+/comments/[\w]+",
            str(text),
            re.IGNORECASE,
        )
    )

def first_reddit_url_in_text(text: str) -> Optional[str]:
    return _extract_first_reddit_url(text)

def incoming_has_reddit_share_path(text: str) -> bool:
    return bool(re.search(r"reddit\.com/r/[\w_]+/s/[a-zA-Z0-9]+", str(text or ""), re.IGNORECASE))

def reddit_share_slug_from_incoming(text: str) -> Optional[str]:
    m = re.search(r"/r/[\w_]+/s/([a-zA-Z0-9]+)", str(text or ""), re.IGNORECASE)
    return m.group(1) if m else None

def count_tool_messages_named(messages: list[Any], tool_name: str) -> int:
    n = 0
    for m in messages or []:
        if isinstance(m, ToolMessage) and (getattr(m, "name", None) or "") == tool_name:
            n += 1
    return n

def reddit_tool_message_no_data(msg: Any) -> bool:
    if not isinstance(msg, ToolMessage):
        return False
    name = str(getattr(msg, "name", "") or "").strip()
    if not name.startswith("reddit_"):
        return False
    content = str(getattr(msg, "content", "") or "")
    low = content.lower()
    if "not found" in low:
        return True
    if '"posts": []' in content:
        return True
    return False

def _tc_args_as_dict(tc: Any) -> dict[str, Any]:
    if isinstance(tc, dict):
        args = tc.get("args")
        if isinstance(args, dict):
            return dict(args)
        raw = tc.get("arguments")
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return dict(parsed)
            except Exception:
                pass
    return {}

def patch_ai_reddit_share_tool_calls(resp: Any, share_url: str, *, attempt_index: int = 0) -> Any:
    """
    Fallback si no hubo resolución HTTP a URL /comments/ en agent_node: el slug /s/ no es post_id.
    Reescribe get_post (o search con query=URL) → reddit_search_reddit con query shortlink.
    El camino preferido sigue siendo _resolve_reddit_share_url_to_comments_url + reddit_get_post.
    """
    if not share_url or not incoming_has_reddit_share_path(share_url):
        return resp
    tcs = list(getattr(resp, "tool_calls", None) or [])
    if not tcs:
        return resp
    _q_safe = reddit_share_search_query_for_attempt(share_url, attempt_index)
    patched: list[Any] = []
    changed = False
    for tc in tcs:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
        tid = (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)) or ""
        if name == "reddit_get_post":
            patched.append(
                {"name": "reddit_search_reddit", "args": {"query": _q_safe}, "id": tid}
            )
            changed = True
            continue
        if name == "reddit_search_reddit":
            if isinstance(tc, dict):
                args = _tc_args_as_dict(tc)
                args["query"] = _q_safe
                new_tc = {**tc, "args": args}
                new_tc.pop("arguments", None)
                patched.append(new_tc)
                changed = True
                continue
            try:
                base = getattr(tc, "args", None)
                args = dict(base) if isinstance(base, dict) else {}
                args["query"] = _q_safe
                patched.append(tc.model_copy(update={"args": args}))
                changed = True
            except Exception:
                patched.append(tc)
            continue
        patched.append(tc)
    if not changed:
        return resp
    return resp.model_copy(update={"tool_calls": patched})

def is_schema_query(text: str) -> bool:
    return incoming_is_schema_query_heuristic(text)


def is_latest_game_query(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    return bool(
        re.search(r"\b(ultima|última|mas\s+reciente|más\s+reciente)\s+partida\b", t)
    ) or ("partida" in t and ("ultima" in t or "última" in t or "reciente" in t))
