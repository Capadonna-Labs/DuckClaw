"""
Compacta salidas JSON de mcp-reddit antes del historial del LLM (anti-OOM / KV cache).
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

from langchain_core.messages import ToolMessage

from duckclaw.integrations.llm_providers import strip_markdown_json_fence


def _stringify_lc_tool_content(content: Any) -> str:
    """Misma semántica que conversation_traces._stringify_lc_message_content (bloques OpenAI)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content.lstrip("\ufeff")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
                else:
                    c = block.get("content")
                    if isinstance(c, str):
                        parts.append(c)
                    elif isinstance(c, list):
                        parts.append(_stringify_lc_tool_content(c))
            else:
                parts.append(str(block))
        return "".join(parts).lstrip("\ufeff")
    return str(content).lstrip("\ufeff")


def _reddit_mcp_llm_max_posts_from_env() -> int:
    raw = (os.environ.get("REDDIT_MCP_LLM_MAX_POSTS") or "").strip()
    if raw.isdigit():
        return max(1, min(50, int(raw)))
    return 8


# Límite de posts en el Markdown enviado al modelo (además del truncado por post).
REDDIT_MCP_LLM_MAX_POSTS = _reddit_mcp_llm_max_posts_from_env()
_TITLE_MAX_CHARS = 140
_SELFTEXT_LLM_MAX_CHARS = 200


def _strip_leading_worker_label(s: str) -> str:
    """Quita prefijos tipo `finanz 2` antes del JSON."""
    t = (s or "").strip()
    if not t:
        return t
    first, _, rest = t.partition("\n")
    if first.strip().startswith("{") or "```" in first:
        return t
    if re.match(r"^[\w.-]+\s+\d+\s*$", first.strip()):
        return rest.strip() if rest.strip() else t
    return t


def _extract_json_dict(s: str) -> dict[str, Any] | None:
    raw = _strip_leading_worker_label(strip_markdown_json_fence(s))
    i = raw.find("{")
    if i < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw[i:])
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _normalize_reddit_url(link: str) -> str:
    link = link.strip()
    if not link:
        return ""
    if link.startswith("http"):
        return link
    return "https://reddit.com" + (link if link.startswith("/") else "/" + link)


def _score_label(score: Any) -> str:
    if isinstance(score, (int, float)):
        return str(int(score))
    if isinstance(score, str) and score.strip():
        return score.strip()
    return "—"


def _truncate_one_line(text: str, max_chars: int) -> str:
    t = text.replace("\n", " ").strip()
    if len(t) <= max_chars:
        return t
    return t[: max_chars - 1] + "…"


def format_reddit_mcp_json_to_nl(
    reply: str, *, max_posts: int = REDDIT_MCP_LLM_MAX_POSTS
) -> str | None:
    """
    Si ``reply`` parsea a un dict con ``posts`` (listado MCP), devuelve Markdown compacto.
    Si no aplica, devuelve ``None``.
    """
    data = _extract_json_dict(reply)
    if not data:
        return None

    if data.get("success") is False:
        err = data.get("error")
        if err is not None:
            return f"**Reddit:** no se pudo obtener el contenido.\n{err}"
        return "**Reddit:** no se pudo obtener el contenido."

    posts = data.get("posts")
    if not isinstance(posts, list) or not posts:
        return None

    first = posts[0]
    if not isinstance(first, dict) or "title" not in first:
        return None

    cap = max(1, max_posts)
    included: list[dict[str, Any]] = []
    for p in posts:
        if len(included) >= cap:
            break
        if isinstance(p, dict) and "title" in p:
            included.append(p)

    if not included:
        return None

    sub = str(data.get("subreddit") or "reddit").strip() or "reddit"
    n = len(included)
    lines: list[str] = [f"## r/{sub} (Top {n} posts)", ""]

    for p in included:
        title = str(p.get("title") or "(sin título)").strip().replace("\n", " ")
        if len(title) > _TITLE_MAX_CHARS:
            title = title[: _TITLE_MAX_CHARS - 1] + "…"
        score_s = _score_label(p.get("score"))
        link = _normalize_reddit_url(str(p.get("permalink") or p.get("url") or ""))
        if link:
            bullet = f"- **{title}** (Score: {score_s}) - [Enlace]({link})"
        else:
            bullet = f"- **{title}** (Score: {score_s})"
        lines.append(bullet)
        st = str(p.get("selftext") or "").strip()
        if st and p.get("is_self"):
            excerpt = _truncate_one_line(st, _SELFTEXT_LLM_MAX_CHARS)
            lines.append(f"  *Extracto:* {excerpt}")
        lines.append("")

    return "\n".join(lines).strip()


def format_reddit_mcp_reply_if_applicable(reply: str) -> str:
    """Devuelve Markdown compacto si reconoce JSON Reddit; si no, ``reply`` sin cambios."""
    if not (reply or "").strip():
        return reply
    out = format_reddit_mcp_json_to_nl(reply)
    return out if out is not None else reply


def sanitize_reddit_tool_messages_for_llm(messages: list[Any]) -> list[Any]:
    """
    Antes de cada invoke del LLM: compacta JSON de mcp-reddit en ``ToolMessage`` (reddit_*).

    Idempotente con ``tools_node``; cubre regresiones o rutas que inserten resultados crudos.
    """
    if not messages:
        return list(messages) if messages is not None else []
    out: list[Any] = []
    for m in messages:
        if isinstance(m, ToolMessage):
            name = (getattr(m, "name", None) or "").strip()
            if name.startswith("reddit_"):
                text = _stringify_lc_tool_content(getattr(m, "content", None))
                new_content = format_reddit_mcp_reply_if_applicable(text)
                out.append(
                    ToolMessage(
                        content=new_content,
                        tool_call_id=m.tool_call_id,
                        name=name,
                    )
                )
                continue
        out.append(m)
    return out
