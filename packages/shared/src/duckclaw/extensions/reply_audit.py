"""Extension hooks that audit/rewrite a worker's final reply before egress.

Each hook is ``hook(*, reply, messages, state, spec, db) -> (reply, state, retry_messages)``.
``retry_messages`` (a list of messages) asks the graph to loop back to the agent once more
with those messages appended; ``None`` keeps the (possibly rewritten) reply. Domain
rules (e.g. a vertical's numeric-claim checks) live in the extension, never in core.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from duckclaw.extensions.skills import _build_hooks

_log = logging.getLogger(__name__)

_HOOKS_CACHE: list[Callable[..., Any]] | None = None


def get_reply_audit_hooks() -> list[Callable[..., Any]]:
    global _HOOKS_CACHE
    if _HOOKS_CACHE is None:
        _HOOKS_CACHE = _build_hooks("reply_audit_hooks", "DUCKCLAW_REPLY_AUDIT_HOOKS")
    return _HOOKS_CACHE


def invoke_extension_reply_audit_hooks(
    *,
    reply: str,
    messages: list[Any],
    state: dict[str, Any],
    spec: Any,
    db: Any,
) -> tuple[str, dict[str, Any], list[Any] | None]:
    """Run hooks in order; the first one that requests a retry wins. Broken hooks are skipped."""
    for hook in get_reply_audit_hooks():
        try:
            reply, state, retry = hook(reply=reply, messages=messages, state=state, spec=spec, db=db)
        except Exception:
            _log.debug("reply audit hook failed: %s", getattr(hook, "__name__", hook), exc_info=True)
            continue
        if retry:
            return reply, state, list(retry)
    return reply, state, None
