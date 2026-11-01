"""databento_query: cost cap, schema allowlist, microstructure summary, key never in the output."""
from __future__ import annotations

import json
from unittest import mock

from duckclaw.forge.skills import databento_bridge as d

KEY = "db-SECRETKEY"


def _call(post, **kw):
    with mock.patch("duckclaw.integration_secrets.resolve_integration_api_key", return_value=kw.pop("key", KEY)), mock.patch(
        "duckclaw.forge.skills.tailscale_bridge._hub_db", return_value=None
    ):
        return d._databento_query_impl(object(), "t", "XNAS.ITCH", "AAPL", kw.pop("schema", "trades"), "2026-10-01T14:30", "2026-10-01T14:31", post=post, **kw)


def test_summary_vwap_imbalance_and_spread() -> None:
    rows = [
        {"price": 10.0, "size": 3, "side": "B", "action": "T", "levels": [{"bid_px_00": 9.99, "ask_px_00": 10.01, "bid_sz_00": 30, "ask_sz_00": 10}]},
        {"price": 11.0, "size": 1, "side": "A", "action": "T", "levels": [{"bid_px_00": 10.99, "ask_px_00": 11.01, "bid_sz_00": 10, "ask_sz_00": 10}]},
    ]
    out = d.summarize_rows("tbbo", rows)
    assert out["vwap"] == 10.25 and out["desbalance"] == 0.5 and out["spread_medio"] == 0.02 and out["desbalance_mejor_nivel"] == 0.25


def test_over_budget_query_is_refused_before_downloading() -> None:
    calls = []

    def post(key, method, params):
        calls.append(method)
        return "9.0"

    assert "rechazada" in _call(post) and calls == ["metadata.get_cost"]


def test_ok_query_returns_cost_and_never_the_key() -> None:
    def post(key, method, params):
        return "0.01" if method == "metadata.get_cost" else json.dumps({"price": 5.0, "size": 2, "side": "B"}) + "\n"

    out = _call(post)
    assert json.loads(out)["costo_usd"] == 0.01 and KEY not in out


def test_unknown_schema_and_missing_key() -> None:
    assert "no permitido" in _call(lambda *a: "0", schema="mbo")
    assert "no está configurado" in _call(lambda *a: "0", key="")
