"""Fast-reply helpers for manager smalltalk shortcuts."""

from __future__ import annotations

from duckclaw.prompt_policies import PromptPolicyResolver


def _manager_greeting_fast_path_ok(incoming: str) -> bool:
    """Short greeting without fly command: skip manager planning and worker delegation."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.graphs.on_the_fly_commands import _is_simple_greeting

    return _is_simple_greeting(raw)


def _manager_capabilities_fast_path_ok(incoming: str) -> bool:
    """Capabilities smalltalk: respuesta directa sin subagente."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.graphs.on_the_fly_commands import _is_capabilities_smalltalk

    return _is_capabilities_smalltalk(raw)


def _greeting_fast_reply_text(worker_id: str | None) -> str:
    worker = (worker_id or "").strip()
    if worker:
        return f"Hola. Aquí {worker}. ¿En qué puedo ayudarte?"
    return "Hola. ¿En qué puedo ayudarte?"


def _capabilities_fast_reply_text(
    worker_id: str | None,
    *,
    coordinator_id: str | None = None,
    delegation_pool: list[str] | None = None,
    prompt_policies: PromptPolicyResolver | None = None,
) -> str:
    if prompt_policies is None:
        raise RuntimeError(
            "capabilities fast reply requires an injected PromptPolicyResolver "
            "with a migrated DuckDB connection"
        )
    coord = (coordinator_id or "").strip()
    pool = [worker for worker in (delegation_pool or []) if (worker or "").strip()]
    if coord and pool:
        lines = "\n".join(f"- {worker}" for worker in pool)
        return prompt_policies.format("capability", "axis_coordinator", coord=coord, lines=lines)
    worker = (worker_id or "").strip()
    if worker:
        return prompt_policies.format("capability", "generic_worker", worker_id=worker)
    return prompt_policies.load("capability", "default_fallback")


__all__ = [
    "_capabilities_fast_reply_text",
    "_greeting_fast_reply_text",
    "_manager_capabilities_fast_path_ok",
    "_manager_greeting_fast_path_ok",
]
