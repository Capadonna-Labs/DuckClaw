"""
Aplana mensajes ChatML/OpenAI a solo user/assistant para tokenizers Gemma (sin roles system/tool).

Spec: specs/features/Formateo de Datasets (SFT & GRPO).md
"""

from __future__ import annotations

import json
from typing import Any

_TOOL_CALLS_JSON_MARKER = "[TOOL_CALLS_JSON]"


def _normalize_tool_calls_for_json(tool_calls: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tc in tool_calls or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if tc.get("type") == "function" else tc.get("function")
        if isinstance(fn, dict):
            name = (fn.get("name") or "").strip()
            raw_args = fn.get("arguments")
        else:
            name = (tc.get("name") or "").strip()
            raw_args = tc.get("arguments")
        args: Any
        if raw_args is None:
            args = {}
        elif isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {"_raw": raw_args}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {"_raw": raw_args}
        if name or args:
            out.append({"name": name, "arguments": args})
    return out


def _assistant_content_with_tool_calls(
    content: str | None,
    tool_calls: list[Any] | None,
) -> str | None:
    parts: list[str] = []
    text = (content or "").strip()
    if text:
        parts.append(text)
    normalized = _normalize_tool_calls_for_json(list(tool_calls or []))
    if normalized:
        parts.append(f"{_TOOL_CALLS_JSON_MARKER}\n{json.dumps(normalized, ensure_ascii=False)}")
    if not parts:
        return None
    return "\n\n".join(parts)


def _expand_raw_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    buffer_sys: list[str] = []
    out: list[dict[str, str]] = []

    def flush_sys_prefix() -> str:
        if not buffer_sys:
            return ""
        prefix = "\n\n".join(s.strip() for s in buffer_sys if s and str(s).strip())
        buffer_sys.clear()
        return prefix

    i = 0
    n = len(messages)
    while i < n:
        m = messages[i]
        if not isinstance(m, dict):
            i += 1
            continue
        role = (m.get("role") or "").strip().lower()
        if role == "system":
            c = m.get("content")
            s = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            if s and str(s).strip():
                buffer_sys.append(str(s).strip())
            i += 1
            continue
        if role == "user":
            c = m.get("content")
            uc = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            prefix = flush_sys_prefix()
            if prefix:
                uc = f"{prefix}\n\n{(uc or '').strip()}".strip() if (uc or "").strip() else prefix
            out.append({"role": "user", "content": uc or ""})
            i += 1
            continue
        if role == "assistant":
            tc = m.get("tool_calls")
            c = m.get("content")
            text = c if isinstance(c, str) else (json.dumps(c, ensure_ascii=False) if c is not None else "")
            merged = _assistant_content_with_tool_calls(text, tc if isinstance(tc, list) else None)
            if merged is None:
                i += 1
                continue
            prefix = flush_sys_prefix()
            if prefix:
                merged = f"{prefix}\n\n{merged}".strip()
            out.append({"role": "assistant", "content": merged})
            i += 1
            continue
        if role == "tool":
            name = (m.get("name") or "tool").strip() or "tool"
            c = m.get("content")
            body = c if isinstance(c, str) else json.dumps(c, ensure_ascii=False)
            prefix = flush_sys_prefix()
            line = f"[RESULTADO DE HERRAMIENTA {name}]: {body}" if body else f"[RESULTADO DE HERRAMIENTA {name}]:"
            if prefix:
                line = f"{prefix}\n\n{line}"
            out.append({"role": "user", "content": line})
            i += 1
            continue
        i += 1

    if buffer_sys:
        prefix = "\n\n".join(s.strip() for s in buffer_sys if s and str(s).strip())
        if prefix:
            if out and out[0].get("role") == "user":
                first = (out[0].get("content") or "").strip()
                out[0]["content"] = f"{prefix}\n\n{first}".strip() if first else prefix
            else:
                out.insert(0, {"role": "user", "content": prefix})

    return out


def _merge_consecutive_same_role(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    if not rows:
        return []
    merged: list[dict[str, str]] = []
    for row in rows:
        role = row.get("role") or ""
        content = (row.get("content") or "").strip()
        if not merged:
            merged.append({"role": role, "content": content})
            continue
        last = merged[-1]
        if last.get("role") == role:
            prev = (last.get("content") or "").strip()
            last["content"] = f"{prev}\n\n{content}".strip() if prev else content
        else:
            merged.append({"role": role, "content": content})
    return merged


def _ensure_starts_with_user_then_alternate(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    m = _merge_consecutive_same_role([r for r in rows if r.get("role") in ("user", "assistant")])
    if not m:
        return []
    if m[0].get("role") == "assistant":
        m.insert(0, {"role": "user", "content": ""})
    out: list[dict[str, str]] = []
    for row in m:
        want = "user" if len(out) % 2 == 0 else "assistant"
        got = row.get("role") or ""
        content = (row.get("content") or "").strip()
        if got == want:
            out.append({"role": want, "content": row.get("content") or ""})
        else:
            out.append({"role": want, "content": ""})
            out.append({"role": got, "content": row.get("content") or ""})
    return out


def flatten_messages_for_gemma(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """
    Transforma la lista de mensajes de la traza a solo user/assistant, alternando.

    - system → prefijado al primer user o assistant según aparezca.
    - tool_calls del assistant → JSON en content bajo marca [TOOL_CALLS_JSON].
    - tool → user con prefijo [RESULTADO DE HERRAMIENTA {name}]: ...
    """
    if not messages:
        return []
    expanded = _expand_raw_messages([dict(x) for x in messages if isinstance(x, dict)])
    return _ensure_starts_with_user_then_alternate(expanded)
