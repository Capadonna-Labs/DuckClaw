"""Flag replies that mark a tool's action as done when the tool never ran this turn.

Zero-trust egress: lighter models sometimes copy an earlier reply's confirmation
template ("create_skill ✅ Guardado en el hub / list_skills ✅ Aparece en el
catálogo") without calling anything. The reply is kept, but a visible note says
those tools did not run, so a fabricated action can't pass as a real one.

ponytail: line-level heuristic (tool name + success marker on the same line). It
can't verify tools run inside a delegate, so it stays silent when the turn
delegated (invoke_worker).
"""

from __future__ import annotations

import re
from typing import Any, Iterable

_SUCCESS_MARKER = re.compile(
    r"✅|✔|☑|\b(?:cread[oa]s?|guardad[oa]s?|ejecutad[oa]s?|enviad[oa]s?|confirmad[oa]s?|"
    r"completad[oa]s?|aplicad[oa]s?|actualizad[oa]s?|registrad[oa]s?|colocad[oa]s?|"
    r"created|saved|executed|sent|confirmed|succeeded|placed)\b",
    re.IGNORECASE,
)
_DELEGATION_TOOLS = {"invoke_worker", "delegate_to_worker"}


def tools_called_since(messages: list[Any], last_human_idx: int) -> set[str]:
    """Tool names requested or answered after the last human message."""
    from langchain_core.messages import AIMessage, ToolMessage

    names: set[str] = set()
    for m in (messages or [])[max(0, last_human_idx + 1):]:
        if isinstance(m, ToolMessage):
            names.add(str(getattr(m, "name", "") or "").strip())
        elif isinstance(m, AIMessage):
            for tc in getattr(m, "tool_calls", None) or []:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                names.add(str(name or "").strip())
    names.discard("")
    return names


def unexecuted_tool_claims(reply: str, called: set[str], known_tools: Iterable[str]) -> list[str]:
    """Known tool names the reply marks as done (same line as a success marker) but never ran."""
    if not reply or called & _DELEGATION_TOOLS:
        return []
    # Only snake_case names: plain words ("search") would match ordinary prose.
    candidates = sorted({t for t in known_tools if "_" in t and t not in called}, key=len, reverse=True)
    found: list[str] = []
    for line in reply.splitlines():
        if not _SUCCESS_MARKER.search(line):
            continue
        for tool in candidates:
            if tool not in found and re.search(rf"(?<![\w.]){re.escape(tool)}(?![\w])", line):
                found.append(tool)
    return found


def append_unexecuted_claims_warning(
    reply: str, messages: list[Any], last_human_idx: int, known_tools: Iterable[str]
) -> str:
    claims = unexecuted_tool_claims(reply, tools_called_since(messages, last_human_idx), known_tools)
    if not claims:
        return reply
    names = ", ".join(f"`{c}`" for c in claims)
    return (
        f"{reply.rstrip()}\n\n> ⚠️ **Verificación automática:** este mensaje da por hecho {names}, "
        "pero esas herramientas no se ejecutaron en este turno. Trátalo como no realizado."
    )
