"""Status chrome for DuckClaw sovereign TUI chat (OpenCode-inspired)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def resolve_tui_llm_label(repo_root: Path) -> str:
    """Best-effort provider · model label from gateway .env."""

    env_path = repo_root / ".env"
    prov = (os.environ.get("DUCKCLAW_LLM_PROVIDER") or "").strip()
    model = (os.environ.get("DUCKCLAW_LLM_MODEL") or "").strip()
    if env_path.is_file():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                k = key.strip()
                v = val.strip().strip("'\"")
                if k == "DUCKCLAW_LLM_PROVIDER" and v and not prov:
                    prov = v
                if k == "DUCKCLAW_LLM_MODEL" and v and not model:
                    model = v
        except OSError:
            pass
    prov = prov or "env"
    model = model or "default"
    return f"{prov} · {model}"


def format_usage_tokens(usage: Any) -> str:
    if not isinstance(usage, dict):
        return ""
    total = usage.get("total_tokens")
    if total is None:
        prompt = usage.get("prompt_tokens") or usage.get("input_tokens")
        completion = usage.get("completion_tokens") or usage.get("output_tokens")
        if prompt is not None or completion is not None:
            total = int(prompt or 0) + int(completion or 0)
    if total is None:
        return ""
    try:
        n = int(total)
    except (TypeError, ValueError):
        return ""
    if n >= 1000:
        return f"{n / 1000:.1f}K tok"
    return f"{n} tok"


def format_chat_status_bar(
    *,
    worker_id: str,
    tenant_id: str,
    llm_label: str,
    usage: Any = None,
) -> str:
    parts = [
        f"[cyan]{llm_label}[/]",
        f"worker [bold]{worker_id}[/]",
        f"tenant [dim]{tenant_id}[/]",
    ]
    tok = format_usage_tokens(usage)
    if tok:
        parts.append(f"[yellow]{tok}[/]")
    return " · ".join(parts)


def format_chat_shortcuts_hint() -> str:
    return (
        "[dim]/workers[/] cambiar agente · "
        "[dim]/status[/] contexto · "
        "[dim]/web[/] consola · "
        "[dim]/quit[/] salir"
    )
