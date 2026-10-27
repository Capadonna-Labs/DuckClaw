"""Admin read of tool_call_log: per-tool summary, latest calls, tenant scoping, empty before the first call."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

_gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from routers.admin_domains import mcp_activity  # noqa: E402
from duckclaw.write_handlers.usage_logs import _apply_append_tool_call_log  # noqa: E402


class _Db:
    """The slice of DuckClaw that the reader uses: ``query`` returns a JSON string of rows."""

    def __init__(self, con) -> None:
        self.con = con

    def query(self, sql: str) -> str:
        cur = self.con.execute(sql)
        cols = [d[0] for d in cur.description]
        return json.dumps([dict(zip(cols, r)) for r in cur.fetchall()], default=str)


def _seed() -> _Db:
    con = duckdb.connect(":memory:")
    rows = [("mcp_tailscale", "list_devices", "ok", 100), ("mcp_tailscale", "list_devices", "ok", 300), ("mcp_tailscale", "list_devices", "error", 200),
            ("mcp_hf", "hub_repo_search", "ok", 50)]
    for i, (c, t, s, ms) in enumerate(rows):
        _apply_append_tool_call_log(con, {"id": f"T{i}", "tenant_id": "default", "connector_id": c, "tool_name": t, "status": s, "duration_ms": ms, "error": "timeout" if s == "error" else ""})
    _apply_append_tool_call_log(con, {"id": "OTHER", "tenant_id": "other", "connector_id": "mcp_x", "tool_name": "x"})
    return _Db(con)


def test_summary_counts_errors_and_average_per_tool_and_is_tenant_scoped() -> None:
    out = mcp_activity.read_activity(_seed(), "default", days=7, limit=50)
    assert out["table_ready"] is True
    top = out["summary"][0]
    assert (top["connector_id"], top["tool_name"], top["calls"], top["errors"], top["avg_ms"]) == ("mcp_tailscale", "list_devices", 3, 1, 200)
    assert {r["connector_id"] for r in out["summary"]} == {"mcp_tailscale", "mcp_hf"}          # the other tenant's call is not visible
    assert len(out["recent"]) == 4 and out["recent"][0]["created_at"]


def test_connector_filter_and_limit() -> None:
    out = mcp_activity.read_activity(_seed(), "default", days=7, limit=2, connector_id="mcp_tailscale")
    assert len(out["recent"]) == 2 and {r["connector_id"] for r in out["recent"]} == {"mcp_tailscale"}
    assert [r["calls"] for r in out["summary"]] == [3]


def test_quotes_in_filters_cannot_break_out_of_the_query() -> None:
    out = mcp_activity.read_activity(_seed(), "default", days=7, limit=5, connector_id="x' OR '1'='1")
    assert out["table_ready"] is True and out["summary"] == [] and out["recent"] == []


def test_empty_until_the_first_call_is_recorded() -> None:
    out = mcp_activity.read_activity(_Db(duckdb.connect(":memory:")), "default", days=7, limit=5)
    assert out == {"table_ready": False, "summary": [], "recent": []}


def test_router_is_mounted_in_the_admin_api() -> None:
    src = (_gw / "routers" / "admin.py").read_text(encoding="utf-8")
    assert "router.include_router(mcp_activity_router)" in src
