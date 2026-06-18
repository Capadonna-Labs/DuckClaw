"""DuckClaw shared: integrations, utils, bi, ops."""

from __future__ import annotations

import pkgutil

__path__ = pkgutil.extend_path(__path__, __name__)


def __getattr__(name: str):
    if name == "DuckClaw":
        from duckclaw.db_bridge import DuckClaw as _DuckClaw

        globals()["DuckClaw"] = _DuckClaw
        return _DuckClaw
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | {"DuckClaw"})
