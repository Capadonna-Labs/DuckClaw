"""Regression tests for deterministic position metrics (unsigned SL/TP distances)."""

from __future__ import annotations

import json

from duckclaw.position_metrics import (
    POSITION_METRICS_RETRY_REASON,
    calculate_deleveraging_tranche,
    calculate_pnl_contribution,
    calculate_tp_sl_distance,
    enforce_position_metrics_rule,
    infer_side,
    reply_claims_tp_sl_pct,
)


def test_infer_side_long_and_short() -> None:
    assert infer_side(100.0, 95.0, 110.0) == "long"
    assert infer_side(100.0, 105.0, 90.0) == "short"
    assert infer_side(100.0, 110.0, 105.0) == "ambiguous"


def test_long_standard_distances() -> None:
    # Incident-style long: price 100, SL 95 (-5%), TP 110 (+10%) → RR 2.0
    out = calculate_tp_sl_distance(100, 95, 110)
    assert out["ok"] is True
    assert out["side"] == "long"
    assert out["dist_sl_pct"] == 5.0
    assert out["dist_tp_pct"] == 10.0
    assert out["rr_ratio"] == 2.0
    # Magnitudes never negative (sign-inversion regression).
    assert out["dist_sl_pct"] >= 0
    assert out["dist_tp_pct"] >= 0


def test_short_standard_distances() -> None:
    out = calculate_tp_sl_distance(100, 105, 90)
    assert out["ok"] is True
    assert out["side"] == "short"
    assert out["dist_sl_pct"] == 5.0
    assert out["dist_tp_pct"] == 10.0
    assert out["rr_ratio"] == 2.0


def test_price_near_sl_long() -> None:
    # Near SL: tiny remaining SL distance, large TP distance.
    out = calculate_tp_sl_distance(95.5, 95.0, 110.0)
    assert out["ok"] is True
    assert out["side"] == "long"
    assert out["dist_sl_pct"] == round(abs(95.5 - 95.0) / 95.5 * 100, 4)
    assert out["dist_tp_pct"] == round(abs(110.0 - 95.5) / 95.5 * 100, 4)
    assert out["dist_sl_pct"] > 0
    assert out["dist_tp_pct"] > out["dist_sl_pct"]


def test_price_near_tp_long() -> None:
    out = calculate_tp_sl_distance(109.0, 95.0, 110.0)
    assert out["ok"] is True
    assert out["side"] == "long"
    assert out["dist_tp_pct"] == round(abs(110.0 - 109.0) / 109.0 * 100, 4)
    assert out["dist_sl_pct"] == round(abs(109.0 - 95.0) / 109.0 * 100, 4)
    assert out["dist_tp_pct"] < out["dist_sl_pct"]


def test_rejects_equal_levels_and_bad_price() -> None:
    bad = calculate_tp_sl_distance(100, 100, 100)
    assert bad["ok"] is False
    assert "iguales" in (bad.get("error") or "")

    zero = calculate_tp_sl_distance(0, 95, 110)
    assert zero["ok"] is False

    amb = calculate_tp_sl_distance(100, 90, 80)
    assert amb["ok"] is False
    assert amb["side"] == "ambiguous"


def test_string_numeric_inputs() -> None:
    out = calculate_tp_sl_distance("100.0", "95", "110")
    assert out["ok"] is True
    assert out["dist_sl_pct"] == 5.0


def test_pnl_contribution() -> None:
    out = calculate_pnl_contribution(250, 1000)
    assert out["ok"] is True
    assert out["contribution_pct"] == 25.0

    neg = calculate_pnl_contribution(-100, 400)
    assert neg["ok"] is True
    assert neg["contribution_pct"] == -25.0

    zero = calculate_pnl_contribution(10, 0)
    assert zero["ok"] is False


def test_deleveraging_tranche() -> None:
    out = calculate_deleveraging_tranche(40, 20, 4)
    assert out["ok"] is True
    assert out["gap_pct_points"] == 20.0
    assert out["tranche_pct_points"] == 5.0

    bad_steps = calculate_deleveraging_tranche(40, 20, 0)
    assert bad_steps["ok"] is False


def test_reply_claims_and_egress_guard() -> None:
    claim = "Distancia a SL: 5.2% · TP a 3.1% · RR 1.5"
    assert reply_claims_tp_sl_pct(claim) is True
    assert reply_claims_tp_sl_pct("Mercado calmado, sin niveles.") is False

    blocked, reason = enforce_position_metrics_rule(
        reply=claim, messages=[], enabled=True
    )
    assert reason == POSITION_METRICS_RETRY_REASON
    assert "calculate_tp_sl_distance" in blocked

    ok_msg, ok_reason = enforce_position_metrics_rule(
        reply=claim, messages=[], enabled=False
    )
    assert ok_reason is None
    assert ok_msg == claim

    class _TM:
        name = "calculate_tp_sl_distance"
        content = '{"ok": true, "dist_sl_pct": 5.2, "dist_tp_pct": 3.1}'

    passed, reason2 = enforce_position_metrics_rule(
        reply=claim, messages=[_TM()], enabled=True
    )
    assert reason2 is None
    assert passed == claim


def test_strip_tp_sl_pct_claims_keeps_report_body() -> None:
    from duckclaw.position_metrics import strip_tp_sl_pct_claims

    draft = (
        "## /loop · Diagnóstico\n"
        "P4 monitoreo OK.\n"
        "Distancia a SL: 5.2% · TP a 3.1%\n"
        "Siguiente: /loop-approve si HITL."
    )
    out = strip_tp_sl_pct_claims(draft)
    assert "Diagnóstico" in out
    assert "P4 monitoreo OK" in out
    assert "5.2%" not in out
    assert "3.1%" not in out


def test_strip_preserves_gfm_table_separator() -> None:
    """Regression: dropping |---| made playground render TP/SL as one paragraph."""
    from duckclaw.position_metrics import strip_tp_sl_pct_claims

    draft = (
        "### P4 · TP/SL — 5 niveles ACTIVE\n"
        "\n"
        "| Ticker | Precio | SL | TP | Dist SL% | Dist TP% | R:R |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
        "| CEG | $267.37 | $245.00 | $300.00 | 8.37% | 12.20% | 1.46 |\n"
        "| TLT | $85.35 | $80.00 | $87.00 | 6.27% | 1.93% | 0.31 |\n"
        "\n"
        "Distancia a SL: 5.2% en prosa suelta.\n"
    )
    out = strip_tp_sl_pct_claims(draft)
    assert "| --- | --- | --- | --- | --- | --- | --- |" in out
    assert "| CEG |" in out and "8.37%" in out
    assert "5.2%" not in out  # prose claim stripped
    assert "prosa suelta" in out


def test_deterministic_rewrite_from_homeostasis_levels() -> None:
    from duckclaw.position_metrics import apply_deterministic_tp_sl_rewrite

    class _TM:
        name = "evaluate_homeostasis"
        content = json.dumps(
            {
                "ok": True,
                "tp_sl_monitor": {
                    "levels": [
                        {
                            "ticker": "CCJ",
                            "price": 100.0,
                            "stop_loss": 95.0,
                            "take_profit": 110.0,
                            "dist_sl_pct": -5.0,  # signed / inverted bait
                            "dist_tp_pct": -10.0,
                            "status": "ACTIVE",
                        }
                    ]
                },
            }
        )

    draft = (
        "## /loop\n"
        "CCJ Distancia a SL: -5.0% · Distancia a TP: -10.0%\n"
        "Monitoreo OK."
    )
    out, meta = apply_deterministic_tp_sl_rewrite(draft, [_TM()])
    assert meta["rewrote"] is True
    assert meta["levels_found"] == 1
    assert "-5.0%" not in out
    assert "Distancia TP/SL (determinística)" in out
    assert "| CCJ |" in out
    assert "| 5.0 |" in out
    assert "| 10.0 |" in out
    assert "| 2.0 |" in out


def test_guard_skips_retry_when_levels_present_without_tool() -> None:
    class _TM:
        name = "evaluate_homeostasis"
        content = (
            '{"tp_sl_monitor":{"levels":[{"ticker":"X","price":100,"stop_loss":95,'
            '"take_profit":110,"status":"ACTIVE"}]}}'
        )

    claim = "Distancia a SL: 5.2%"
    # Levels present → enforce returns None reason (mechanical rewrite handles it).
    msg, reason = enforce_position_metrics_rule(
        reply=claim, messages=[_TM()], enabled=True
    )
    assert reason is None
    assert msg == claim


def test_five_anonymous_tp_sl_tools_do_not_collapse() -> None:
    from duckclaw.position_metrics import extract_tp_sl_level_inputs

    class _TM:
        def __init__(self, price: float, sl: float, tp: float) -> None:
            self.name = "calculate_tp_sl_distance"
            self.content = json.dumps(
                {"ok": True, "price": price, "sl": sl, "tp": tp, "dist_sl_pct": 1.0, "dist_tp_pct": 2.0}
            )

    msgs = [
        _TM(250, 240, 270),
        _TM(95, 93, 98),
        _TM(500, 480, 540),
        _TM(510, 490, 520),
        _TM(90, 88, 95),
    ]
    levels = extract_tp_sl_level_inputs(msgs)
    assert len(levels) == 5


def test_homeostasis_compact_preserves_trailing_levels() -> None:
    from langchain_core.messages import ToolMessage

    from duckclaw.workers.tool_output_truncation import truncate_tool_messages_for_llm
    from duckclaw.position_metrics import extract_tp_sl_level_inputs

    levels = [
        {
            "id": f"id-{t}",
            "ticker": t,
            "price": p,
            "stop_loss": s,
            "take_profit": tp,
            "dist_sl_pct": 1.0,
            "dist_tp_pct": 2.0,
            "status": "ACTIVE",
        }
        for t, p, s, tp in [
            ("CEG", 250.0, 240.0, 270.0),
            ("IEF", 95.0, 93.0, 98.0),
            ("META", 500.0, 480.0, 540.0),
            ("SPY", 510.0, 490.0, 520.0),
            ("TLT", 90.0, 88.0, 95.0),
        ]
    ]
    # Realistic order: huge goals blob first, tp_sl_monitor last.
    raw = json.dumps(
        {
            "status": "success",
            "goals": {
                "domain_goals": [{"belief_key": f"g{i}", "blob": "y" * 400} for i in range(40)],
                "infra": {"x": "z" * 2000},
            },
            "current_metrics": {"a": 1},
            "deviations": {},
            "tp_sl_monitor": {"active_count": 5, "levels": levels},
            "tp_sl_alerts": [],
        },
        ensure_ascii=False,
    )
    assert len(raw) > 8000
    # Naive head cut would drop TLT; compact path must keep all five.
    assert "TLT" not in raw[:8000]

    truncated_msgs = truncate_tool_messages_for_llm(
        [ToolMessage(content=raw, tool_call_id="t1", name="evaluate_homeostasis")],
        8000,
    )
    content = truncated_msgs[0].content
    assert "…[truncado por tamaño]" not in content or "TLT" in content
    extracted = extract_tp_sl_level_inputs(truncated_msgs)
    assert sorted(r["ticker"] for r in extracted) == ["CEG", "IEF", "META", "SPY", "TLT"]


def test_truncated_homeostasis_regex_scan_and_skips_anonymous_tools() -> None:
    from duckclaw.position_metrics import apply_deterministic_tp_sl_rewrite, extract_tp_sl_level_inputs

    levels_json = ",".join(
        json.dumps(
            {
                "id": f"id-{t}",
                "ticker": t,
                "price": p,
                "stop_loss": s,
                "take_profit": tp,
                "dist_sl_pct": 1.0,
                "dist_tp_pct": 2.0,
                "status": "ACTIVE",
            },
            ensure_ascii=False,
        )
        for t, p, s, tp in [
            ("CEG", 250.0, 240.0, 270.0),
            ("IEF", 95.0, 93.0, 98.0),
            ("META", 500.0, 480.0, 540.0),
            ("SPY", 510.0, 490.0, 520.0),
            ("TLT", 90.0, 88.0, 95.0),
        ]
    )
    # Levels appear early enough that a broken JSON still contains all rows.
    raw = '{"status":"success","tp_sl_monitor":{"levels":[' + levels_json + '],"active_count":5}'
    truncated = raw + ',"goals":"' + ("z" * 100) + "\n…[truncado por tamaño]"

    class _TM:
        name = "evaluate_homeostasis"
        content = truncated

    class _Calc:
        def __init__(self, price: float, sl: float, tp: float) -> None:
            self.name = "calculate_tp_sl_distance"
            self.content = json.dumps({"ok": True, "price": price, "sl": sl, "tp": tp})

    msgs = [_TM()] + [
        _Calc(250, 240, 270),
        _Calc(95, 93, 98),
        _Calc(500, 480, 540),
        _Calc(510, 490, 520),
        _Calc(90, 88, 95),
    ]
    levels = extract_tp_sl_level_inputs(msgs)
    tickers = sorted(r["ticker"] for r in levels)
    assert tickers == ["CEG", "IEF", "META", "SPY", "TLT"]

    out, meta = apply_deterministic_tp_sl_rewrite("CEG Distancia a SL: -1.0%\n", msgs)
    assert meta["levels_found"] == 5
    assert "| CEG |" in out and "| TLT |" in out
    assert "| ? |" not in out


def test_top_level_price_does_not_mask_monitor_levels() -> None:
    from duckclaw.position_metrics import extract_tp_sl_level_inputs

    class _TM:
        name = "evaluate_homeostasis"
        content = json.dumps(
            {
                "ok": True,
                "price": 90.0,
                "sl": 88.0,
                "tp": 95.0,
                "tp_sl_monitor": {
                    "levels": [
                        {
                            "ticker": "CEG",
                            "price": 250.0,
                            "stop_loss": 240.0,
                            "take_profit": 270.0,
                            "status": "ACTIVE",
                        },
                        {
                            "ticker": "TLT",
                            "price": 90.0,
                            "stop_loss": 88.0,
                            "take_profit": 95.0,
                            "status": "ACTIVE",
                        },
                    ]
                },
            }
        )

    levels = extract_tp_sl_level_inputs([_TM()])
    assert sorted(r["ticker"] for r in levels) == ["CEG", "TLT"]


def test_merge_null_price_named_with_anonymous_metrics() -> None:
    """Prod pattern: homeostasis levels with price=null + calculate_tp_sl without ticker."""
    from duckclaw.position_metrics import extract_tp_sl_level_inputs

    class _Homeo:
        name = "evaluate_homeostasis"
        content = json.dumps(
            {
                "status": "success",
                "tp_sl_monitor": {
                    "levels": [
                        {
                            "id": "tp_sl_ceg",
                            "ticker": "CEG",
                            "price": None,
                            "stop_loss": 245.0,
                            "take_profit": 300.0,
                            "status": "ACTIVE",
                        },
                        {
                            "id": "tp_sl_tlt",
                            "ticker": "TLT",
                            "price": None,
                            "stop_loss": 80.0,
                            "take_profit": 87.0,
                            "status": "ACTIVE",
                        },
                        {
                            "id": "tp_sl_spy",
                            "ticker": "SPY",
                            "price": None,
                            "stop_loss": 725.0,
                            "take_profit": 800.0,
                            "status": "ACTIVE",
                        },
                        {
                            "id": "tp_sl_ief",
                            "ticker": "IEF",
                            "price": None,
                            "stop_loss": 91.5,
                            "take_profit": 95.0,
                            "status": "ACTIVE",
                        },
                        {
                            "id": "tp_sl_meta",
                            "ticker": "META",
                            "price": None,
                            "stop_loss": 520.0,
                            "take_profit": 680.0,
                            "status": "ACTIVE",
                        },
                    ]
                },
            }
        )

    class _Calc:
        def __init__(self, price: float, sl: float, tp: float) -> None:
            self.name = "calculate_tp_sl_distance"
            self.content = json.dumps({"ok": True, "price": price, "sl": sl, "tp": tp})

    msgs = [
        _Homeo(),
        _Calc(260.0, 245.0, 300.0),
        _Calc(93.0, 91.5, 95.0),
        _Calc(600.0, 520.0, 680.0),
        _Calc(760.0, 725.0, 800.0),
        _Calc(84.0, 80.0, 87.0),
    ]
    levels = extract_tp_sl_level_inputs(msgs)
    assert sorted(r["ticker"] for r in levels) == ["CEG", "IEF", "META", "SPY", "TLT"]
    assert all(r["price"] is not None for r in levels)


def test_price_hint_from_fetch_market_data_when_homeo_missing() -> None:
    from duckclaw.position_metrics import extract_tp_sl_level_inputs

    class _Mkt:
        name = "fetch_market_data"
        content = json.dumps({"ticker": "TLT", "close": 84.0})

    class _Calc:
        name = "calculate_tp_sl_distance"
        content = json.dumps({"ok": True, "price": 84.0, "sl": 80.0, "tp": 87.0})

    levels = extract_tp_sl_level_inputs([_Mkt(), _Calc()])
    assert len(levels) == 1
    assert levels[0]["ticker"] == "TLT"


def test_read_sql_quoted_stop_loss_merges_anonymous_calcs() -> None:
    """Prod 18:29: no evaluate_homeostasis; read_sql returns stringified SL/TP."""
    from duckclaw.position_metrics import extract_tp_sl_level_inputs

    class _SQL:
        name = "read_sql"
        content = json.dumps(
            [
                {
                    "id": "tp_sl_ceg_20260806",
                    "ticker": "CEG",
                    "stop_loss": "245.0",
                    "take_profit": "300.0",
                    "status": "ACTIVE",
                },
                {
                    "id": "tp_sl_tlt_20260806",
                    "ticker": "TLT",
                    "stop_loss": "80.0",
                    "take_profit": "87.0",
                    "status": "ACTIVE",
                },
                {
                    "id": "tp_sl_spy_20260806",
                    "ticker": "SPY",
                    "stop_loss": "725.0",
                    "take_profit": "800.0",
                    "status": "ACTIVE",
                },
                {
                    "id": "tp_sl_ief_20260806",
                    "ticker": "IEF",
                    "stop_loss": "91.5",
                    "take_profit": "95.0",
                    "status": "ACTIVE",
                },
                {
                    "id": "tp_sl_meta_20260806",
                    "ticker": "META",
                    "stop_loss": "520.0",
                    "take_profit": "680.0",
                    "status": "ACTIVE",
                },
            ]
        )

    class _Calc:
        def __init__(self, price: float, sl: float, tp: float) -> None:
            self.name = "calculate_tp_sl_distance"
            self.content = json.dumps({"ok": True, "price": price, "sl": sl, "tp": tp})

    msgs = [
        _SQL(),
        _Calc(267.37, 245.0, 300.0),
        _Calc(93.0, 91.5, 95.0),
        _Calc(600.0, 520.0, 680.0),
        _Calc(760.0, 725.0, 800.0),
        _Calc(84.0, 80.0, 87.0),
    ]
    levels = extract_tp_sl_level_inputs(msgs)
    assert sorted(r["ticker"] for r in levels) == ["CEG", "IEF", "META", "SPY", "TLT"]
    assert "?" not in [r["ticker"] for r in levels]
