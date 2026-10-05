"""The dashboard status block is prepended only when an existing dashboard is broken."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))


@pytest.mark.parametrize(
    ("status", "injected"),
    [("missing", False), ("valid", False), ("error", False), ("invalid", True)],
)
def test_canvas_block_only_for_invalid_dashboard(monkeypatch, status: str, injected: bool) -> None:
    from duckclaw.forge.skills import custom_reports_bridge
    from routers.admin_domains.playground import canvas_context, vault_access

    class _Db:
        def close(self) -> None:
            pass

    monkeypatch.setattr(vault_access, "open_playground_vault_db", lambda *_a, **_k: _Db())
    monkeypatch.setattr(
        custom_reports_bridge, "_inspect_custom_report_impl", lambda _db, report_id: json.dumps({"status": status})
    )
    out = canvas_context.enrich_message_with_canvas_context(msg="hola", chat_id="admin-conv-1", vault_path="/v.duckdb")
    assert ("[LIENZO_HTML_ESTADO]" in out) is injected
    assert out.endswith("hola")
