"""DuckClaw core: DuckDB bridge. Namespace merge con duckclaw-shared."""

from __future__ import annotations

import pkgutil

__path__ = pkgutil.extend_path(__path__, __name__)

from duckclaw.db_bridge import DuckClaw

__all__ = ["DuckClaw"]
