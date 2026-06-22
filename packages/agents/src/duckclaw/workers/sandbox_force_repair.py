"""Repair agent turns when orchestration forces sandbox but the LLM returns prose."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

# Strix sandbox execution tool ids (framework surface, not domain-specific).
_SANDBOX_EXEC_TOOL_NAMES = frozenset({"execute_sandbox_script", "run_sandbox"})


def is_forced_sandbox_tool(tool_name: str | None) -> bool:
    return str(tool_name or "").strip() in _SANDBOX_EXEC_TOOL_NAMES


def extract_python_from_llm_text(text: str) -> str | None:
    """Recover executable Python when the model ignores tool_choice."""
    body = (text or "").strip()
    if not body:
        return None
    for pattern in (
        r"```(?:python)?\s*\n(.*?)```",
        r"```\s*\n(.*?)```",
    ):
        match = re.search(pattern, body, re.DOTALL | re.IGNORECASE)
        if not match:
            continue
        code = match.group(1).strip()
        if code and any(
            token in code for token in ("import ", "from ", "def ", "print(", "class ")
        ):
            return code
    if body.startswith(("import ", "from ")) and len(body) > 40:
        return body
    return None


def synthesize_sandbox_tool_call(tool_name: str, code: str) -> dict[str, Any]:
    return {
        "name": str(tool_name or "").strip(),
        "args": {"code": code},
        "id": f"call_repair_sandbox_{int(time.time() * 1000)}",
        "type": "tool_call",
    }


def resolve_orchestration_fallback_code(spec: Any) -> str | None:
    """
    Manifest ``tool_orchestration.sandbox_force_fallback_snippet`` relative to worker_dir.

    Workers declare fallback scripts in their own template tree; the framework only reads the path.
    """
    from duckclaw.workers.tool_orchestration import parse_tool_orchestration

    orch = parse_tool_orchestration(spec)
    snippet_rel = (
        getattr(orch, "sandbox_force_fallback_snippet", None) if orch else None
    )
    worker_dir = getattr(spec, "worker_dir", None)
    if not snippet_rel:
        return None
    if not worker_dir:
        return None
    snippet_path = Path(worker_dir) / str(snippet_rel).strip()
    if not snippet_path.is_file():
        return None
    try:
        return snippet_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


__all__ = [
    "extract_python_from_llm_text",
    "is_forced_sandbox_tool",
    "resolve_orchestration_fallback_code",
    "synthesize_sandbox_tool_call",
]
