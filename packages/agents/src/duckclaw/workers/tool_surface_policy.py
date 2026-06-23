"""Turn-level tool surface policy for workers.

These helpers are framework-level gates for tools that should not be exposed to
the LLM on every turn, even when the worker can execute them.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
import re
from typing import Any

STORAGE_IDENTITY_TOOL_NAMES = frozenset({"get_db_path"})
PRIVILEGED_MUTATION_TOOL_NAMES = frozenset({"admin_sql"})
SANDBOX_TOOL_NAMES = frozenset(
    {
        "run_sandbox",
        "run_browser_sandbox",
        "get_browser_session_url",
    }
)
STORAGE_IDENTITY_REQUEST = re.compile(
    r"\b("
    r"get_db_path|"
    r"(nombre|ruta|path|archivo)\s+(de\s+|del\s+|de\s+la\s+|de\s+el\s+)?(db|bd|duckdb|base\s+de\s+datos)|"
    r"(qu[eé]|cu[aá]l)\s+(db|bd|duckdb|base\s+de\s+datos)\s+(usas|usa|est[aá]s\s+usando|est[aá]\s+usando)|"
    r"(db|bd|duckdb|base\s+de\s+datos)\s+(en\s+uso|actual|activa)"
    r")\b",
    re.IGNORECASE,
)
SANDBOX_INTENT_REQUEST = re.compile(
    r"\b("
    r"run_sandbox|run_browser_sandbox|sandbox|"
    r"python|bash|script|c[oó]digo|programa|ejecuta|ejecutar|corre|correr|"
    r"navegador|browser|playwright|selenium|abre\s+https?://|"
    r"gr[aá]fica|grafica|gr[aá]fico|grafico|diagrama|plot|matplotlib|seaborn|plotly"
    r")\b|https?://",
    re.IGNORECASE,
)


def tool_surface_intent_text(user_incoming: str | None, incoming: str | None) -> str:
    """Return the user-authored turn text used for tool surface decisions."""

    original = (user_incoming or "").strip()
    return original or (incoming or "").strip()


def explicit_storage_identity_request(text: str | None) -> bool:
    """Return True when the user asks which DuckDB/storage file is active."""

    return bool(STORAGE_IDENTITY_REQUEST.search(text or ""))


def should_hide_storage_identity_tools(
    incoming: str | None,
    intent_text: str | None,
    *,
    explicit_storage_request: Callable[[str], bool],
) -> bool:
    """Hide storage identity tools unless the turn explicitly asks for storage identity."""

    text = intent_text or incoming or ""
    if explicit_storage_identity_request(text):
        return False
    # Keep the dependency in the signature so callers pass their DB-intent owner,
    # but storage identity is narrower than general DB/schema intent.
    del explicit_storage_request
    return True


def without_tools_named(tools: Iterable[Any], excluded_names: set[str]) -> list[Any]:
    """Return tools excluding names in ``excluded_names``."""

    excluded = {name.strip() for name in excluded_names if name and name.strip()}
    return [
        tool
        for tool in tools
        if str(getattr(tool, "name", "") or "").strip() not in excluded
    ]


def without_storage_identity_tools(tools: Iterable[Any]) -> list[Any]:
    """Hide tools that reveal the active storage identity/path."""

    return without_tools_named(tools, set(STORAGE_IDENTITY_TOOL_NAMES))


def without_privileged_mutation_tools(tools: Iterable[Any]) -> list[Any]:
    """Hide privileged mutation tools from automatic LLM tool choice."""

    return without_tools_named(tools, set(PRIVILEGED_MUTATION_TOOL_NAMES))


def expose_privileged_mutation_tool_names(spec: Any | None) -> frozenset[str]:
    """
    Manifest ``tool_surface.expose_privileged_mutation_tools`` opt-in list.

    Workers that register privileged tools via extensions can expose them in auto-bind
    without hardcoding domain logic in the framework.
    """
    if spec is None:
        return frozenset()
    raw = getattr(spec, "tool_surface_config", None) or {}
    if not isinstance(raw, dict):
        return frozenset()
    items = raw.get("expose_privileged_mutation_tools") or ()
    if isinstance(items, str):
        items = [items]
    if not isinstance(items, (list, tuple)):
        return frozenset()
    return frozenset(str(name).strip() for name in items if str(name).strip())


def without_privileged_mutation_tools_for_auto_bind(
    tools: Iterable[Any],
    *,
    spec: Any = None,
) -> list[Any]:
    """Hide privileged mutation tools except those listed in the worker manifest."""

    exempt = expose_privileged_mutation_tool_names(spec)
    hidden = set(PRIVILEGED_MUTATION_TOOL_NAMES) - set(exempt)
    if not hidden:
        return list(tools)
    return without_tools_named(tools, hidden)


def explicit_sandbox_intent(text: str | None) -> bool:
    """Return True when the user asks for code, browser, plotting, or sandbox execution."""

    return bool(SANDBOX_INTENT_REQUEST.search(text or ""))


def should_hide_sandbox_tools(incoming: str | None, intent_text: str | None) -> bool:
    """Hide sandbox/browser tools unless the turn explicitly asks for execution."""

    return not explicit_sandbox_intent(intent_text or incoming or "")


def without_sandbox_tools(tools: Iterable[Any]) -> list[Any]:
    """Hide sandbox/browser execution tools from automatic LLM tool choice."""

    return without_tools_named(tools, set(SANDBOX_TOOL_NAMES))
