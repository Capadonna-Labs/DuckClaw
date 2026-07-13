from __future__ import annotations

import os
from typing import Any, Callable

from duckclaw.workers.tool_output_truncation import truncate_tool_messages_for_llm

PROVIDER_BUDGET_RUNTIME_DOMAIN = "runtime.provider_budget"
_provider_budget_runtime_db_provider: Callable[[], Any] | None = None


def configure_provider_budget_runtime_db_provider(provider: Callable[[], Any] | None) -> None:
    """Inject DB provider for runtime provider-budget policy lookup."""

    global _provider_budget_runtime_db_provider
    _provider_budget_runtime_db_provider = provider


def _provider_budget_runtime_db(db: Any = None) -> Any:
    if db is not None:
        return db
    provider = _provider_budget_runtime_db_provider
    if provider is None:
        return None
    try:
        return provider()
    except Exception:
        return None


def _runtime_budget_int(
    key: str,
    *,
    env_key: str,
    default: int,
    minimum: int,
    maximum: int,
    db: Any = None,
) -> int:
    runtime_db = _provider_budget_runtime_db(db)
    if runtime_db is not None:
        try:
            from duckclaw.admin_runtime_settings import resolve_runtime_setting

            resolved = resolve_runtime_setting(
                runtime_db,
                tenant_id="global",
                actor_email="",
                domain=PROVIDER_BUDGET_RUNTIME_DOMAIN,
                key=key,
                default="",
            )
            raw_db = str(resolved.get("value") or "").strip()
            if raw_db:
                return max(minimum, min(int(raw_db), maximum))
        except Exception:
            pass

    raw = (os.environ.get(env_key) or "").strip()
    if raw:
        try:
            return max(minimum, min(int(raw), maximum))
        except ValueError:
            pass
    return default


def context_prune_globally_enabled() -> bool:
    """Context monitor activo por defecto; desactivar con DUCKCLAW_CONTEXT_PRUNE_ENABLED=0."""
    raw = (os.environ.get("DUCKCLAW_CONTEXT_PRUNE_ENABLED") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def context_prune_max_estimated_tokens() -> int:
    """
    Umbral de compactación LLM en tokens estimados (chars/4).

    Configurable en millones vía ``DUCKCLAW_CONTEXT_PRUNE_MAX_TOKENS_M`` (default 4).
    """
    raw_m = (os.environ.get("DUCKCLAW_CONTEXT_PRUNE_MAX_TOKENS_M") or "4").strip()
    try:
        millions = float(raw_m)
    except ValueError:
        millions = 4.0
    millions = max(0.5, min(millions, 32.0))
    return int(millions * 1_000_000)


def context_prune_max_messages_default() -> int:
    """Alto por defecto para que el fold dispare casi solo por tokens, no por conteo de msgs."""
    return _runtime_budget_int(
        "context_prune.max_messages",
        env_key="DUCKCLAW_CONTEXT_PRUNE_MAX_MESSAGES",
        default=10_000,
        minimum=2,
        maximum=100_000,
    )


def context_prune_keep_last_messages_default() -> int:
    raw = (os.environ.get("DUCKCLAW_CONTEXT_PRUNE_KEEP_LAST_MESSAGES") or "6").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 6


def context_prune_tool_content_max_chars_default() -> int:
    raw = (os.environ.get("DUCKCLAW_CONTEXT_PRUNE_TOOL_MAX_CHARS") or "8000").strip()
    try:
        return max(500, int(raw))
    except ValueError:
        return 8000


def context_prune_max_estimated_tokens_for_provider(
    provider: str | None = None,
    *,
    db: Any = None,
) -> int:
    """MLX/local inference: fold early (~20k). Cloud providers keep global prune threshold."""
    label = (provider or "").strip().lower()
    if label in ("mlx", "iotcorelabs"):
        return mlx_max_estimated_input_tokens(db=db)
    return context_prune_max_estimated_tokens()


def normalized_context_pruning(
    spec: Any,
    *,
    provider: str | None = None,
    db: Any = None,
) -> dict[str, Any]:
    """
    Política de context monitor: ON por defecto (env global), opt-out en manifest.

    ``context_pruning: { enabled: false }`` en manifest desactiva solo ese worker.
    """
    raw = getattr(spec, "context_pruning_config", None)
    manifest = raw if isinstance(raw, dict) else {}
    if manifest.get("enabled") is False:
        return {}
    if not context_prune_globally_enabled():
        return {}

    cfg = {
        "enabled": True,
        "max_messages": context_prune_max_messages_default(),
        "max_estimated_tokens": context_prune_max_estimated_tokens_for_provider(provider, db=db),
        "keep_last_messages": context_prune_keep_last_messages_default(),
        "tool_content_max_chars": context_prune_tool_content_max_chars_default(),
        "sandbox_heartbeat": bool(manifest.get("sandbox_heartbeat", True)),
    }
    if manifest.get("enabled") is True:
        for key in (
            "max_messages",
            "max_estimated_tokens",
            "keep_last_messages",
            "tool_content_max_chars",
            "sandbox_heartbeat",
        ):
            if key in manifest:
                cfg[key] = manifest[key]

    return {
        "enabled": True,
        "max_messages": max(2, int(cfg["max_messages"])),
        "max_estimated_tokens": max(500, int(cfg["max_estimated_tokens"])),
        "keep_last_messages": max(1, int(cfg["keep_last_messages"])),
        "tool_content_max_chars": max(500, int(cfg["tool_content_max_chars"])),
        "sandbox_heartbeat": bool(cfg["sandbox_heartbeat"]),
    }


def estimate_tokens_from_messages(messages: list[Any]) -> int:
    total = 0
    for message in messages or []:
        content = getattr(message, "content", None) or ""
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(str(part.get("text", "")))
    return max(0, total // 4)


def groq_max_estimated_input_tokens(*, db: Any = None) -> int:
    """
    Estimated chars/4 cap for serialized messages sent to Groq.

    Groq's on-demand tiers count tool schemas too, so this cap stays below
    the advertised request limit to avoid 413 responses.
    """
    return _runtime_budget_int(
        "groq.max_input_tokens",
        env_key="DUCKCLAW_GROQ_MAX_INPUT_TOKENS",
        default=5000,
        minimum=1500,
        maximum=11500,
        db=db,
    )


def groq_tool_message_max_chars(*, db: Any = None) -> int:
    return _runtime_budget_int(
        "groq.tool_message_max_chars",
        env_key="DUCKCLAW_GROQ_TOOL_MESSAGE_MAX_CHARS",
        default=3500,
        minimum=400,
        maximum=100_000,
        db=db,
    )


def trim_messages_to_estimated_cap(
    messages: list[Any],
    *,
    cap: int,
    tool_cap: int,
    note_brand: str,
) -> list[Any]:
    """Trim history and tool output to stay under an estimated chars/4 cap."""
    from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

    msgs = truncate_tool_messages_for_llm(list(messages), tool_cap)

    while len(msgs) > 2 and estimate_tokens_from_messages(msgs) > cap:
        if isinstance(msgs[0], SystemMessage):
            if len(msgs) < 3:
                break
            victim = msgs.pop(1)
            if isinstance(victim, AIMessage) and getattr(victim, "tool_calls", None):
                while len(msgs) > 1 and isinstance(msgs[1], ToolMessage):
                    msgs.pop(1)
        else:
            msgs.pop(0)

    if msgs and isinstance(msgs[0], SystemMessage) and estimate_tokens_from_messages(msgs) > cap:
        sys0 = msgs[0]
        raw_content = getattr(sys0, "content", "") or ""
        content = raw_content if isinstance(raw_content, str) else str(raw_content)
        if content:
            over_tokens = estimate_tokens_from_messages(msgs) - cap
            cut = min(len(content), over_tokens * 4 + 400)
            tail = content[:-cut] if cut < len(content) else content[: max(3000, len(content) // 2)]
            note = (
                f"\n\n[{note_brand}: system prompt truncado por limite de contexto; "
                "prioriza reglas criticas y herramientas.]"
            )
            msgs = [SystemMessage(content=tail + note)] + list(msgs[1:])

    return msgs


def apply_groq_message_budget(messages: list[Any], *, provider: str) -> list[Any]:
    """Trim LangChain messages before invoke when provider is Groq."""
    if (provider or "").strip().lower() != "groq" or not messages:
        return messages
    return trim_messages_to_estimated_cap(
        messages,
        cap=groq_max_estimated_input_tokens(),
        tool_cap=groq_tool_message_max_chars(),
        note_brand="GROQ",
    )


def mlx_max_estimated_input_tokens(*, db: Any = None) -> int:
    """
    Estimated input cap for local MLX/Metal VRAM.

    Very large prompts can OOM mlx_lm; logs usually mention insufficient
    Metal memory.
    """
    return _runtime_budget_int(
        "mlx.max_input_tokens",
        env_key="DUCKCLAW_MLX_MAX_INPUT_TOKENS",
        default=20000,
        minimum=2000,
        maximum=30000,
        db=db,
    )


def mlx_tokens_per_bound_tool_estimate(*, db: Any = None) -> int:
    """Observed ~350 tokens/tool on mlx_lm (68k prompt with 147 tools + 17k msgs)."""
    return _runtime_budget_int(
        "mlx.tokens_per_bound_tool",
        env_key="DUCKCLAW_MLX_TOKENS_PER_BOUND_TOOL",
        default=350,
        minimum=100,
        maximum=800,
        db=db,
    )


def mlx_message_reserve_tokens(*, db: Any = None) -> int:
    return _runtime_budget_int(
        "mlx.message_reserve_tokens",
        env_key="DUCKCLAW_MLX_MESSAGE_RESERVE_TOKENS",
        default=4000,
        minimum=1000,
        maximum=12000,
        db=db,
    )


def mlx_max_bound_tools(*, db: Any = None) -> int:
    base = mlx_max_estimated_input_tokens(db=db)
    reserve = mlx_message_reserve_tokens(db=db)
    per_tool = mlx_tokens_per_bound_tool_estimate(db=db)
    return max(8, (base - reserve) // max(1, per_tool))


def mlx_tool_schema_reserve_tokens(bound_tools_n: int, *, db: Any = None) -> int:
    n = max(0, int(bound_tools_n or 0))
    if n <= 0:
        return 0
    base = mlx_max_estimated_input_tokens(db=db)
    return min(base - 2000, n * mlx_tokens_per_bound_tool_estimate(db=db))


def mlx_effective_message_cap(*, bound_tools_n: int = 0, db: Any = None) -> int:
    return max(2000, mlx_max_estimated_input_tokens(db=db) - mlx_tool_schema_reserve_tokens(bound_tools_n, db=db))


def mlx_tool_message_max_chars(*, db: Any = None) -> int:
    return _runtime_budget_int(
        "mlx.tool_message_max_chars",
        env_key="DUCKCLAW_MLX_TOOL_MESSAGE_MAX_CHARS",
        default=5000,
        minimum=400,
        maximum=80_000,
        db=db,
    )


def apply_mlx_message_budget(
    messages: list[Any],
    *,
    provider: str,
    bound_tools_n: int = 0,
) -> list[Any]:
    if (provider or "").strip().lower() not in ("mlx", "iotcorelabs") or not messages:
        return messages
    return trim_messages_to_estimated_cap(
        messages,
        cap=mlx_effective_message_cap(bound_tools_n=bound_tools_n),
        tool_cap=mlx_tool_message_max_chars(),
        note_brand="MLX",
    )


def apply_provider_input_budget(
    messages: list[Any],
    *,
    provider: str,
    bound_tools_n: int = 0,
) -> list[Any]:
    """Provider-specific context trimming for Groq TPM and MLX VRAM limits."""
    provider_label = (provider or "").strip().lower()
    if provider_label == "groq":
        return apply_groq_message_budget(messages, provider=provider)
    if provider_label in ("mlx", "iotcorelabs"):
        return apply_mlx_message_budget(messages, provider=provider, bound_tools_n=bound_tools_n)
    return messages



def split_for_pruning(non_system: list[Any], keep_last: int) -> tuple[list[Any], list[Any]]:
    """Split old history from the tail while preserving AI tool-call adjacency."""
    from langchain_core.messages import AIMessage, ToolMessage

    if keep_last < 1:
        keep_last = 1
    if len(non_system) <= keep_last:
        return [], non_system[:]
    split_at = len(non_system) - keep_last
    while split_at > 0 and isinstance(non_system[split_at], ToolMessage):
        split_at -= 1
    tail = non_system[split_at:]
    if tail and isinstance(tail[-1], AIMessage):
        last_ai = tail[-1]
        if getattr(last_ai, "tool_calls", None):
            end = len(non_system)
            tail_end = split_at + len(tail)
            while tail_end < end and isinstance(non_system[tail_end], ToolMessage):
                tail_end += 1
            tail = non_system[split_at:tail_end]
    head = non_system[:split_at]
    return head, tail


__all__ = [
    "apply_groq_message_budget",
    "apply_mlx_message_budget",
    "apply_provider_input_budget",
    "configure_provider_budget_runtime_db_provider",
    "context_prune_globally_enabled",
    "context_prune_max_estimated_tokens",
    "context_prune_max_estimated_tokens_for_provider",
    "estimate_tokens_from_messages",
    "groq_max_estimated_input_tokens",
    "groq_tool_message_max_chars",
    "mlx_effective_message_cap",
    "mlx_max_bound_tools",
    "mlx_max_estimated_input_tokens",
    "mlx_tool_message_max_chars",
    "mlx_tool_schema_reserve_tokens",
    "normalized_context_pruning",
    "split_for_pruning",
    "trim_messages_to_estimated_cap",
]
