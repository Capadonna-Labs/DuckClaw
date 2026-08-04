"""Fly outbound charts → admin playground SSE visual fields."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_GW = _REPO / "services" / "api-gateway"
if str(_GW) not in sys.path:
    sys.path.insert(0, str(_GW))


def test_register_and_pop_fly_outbound_charts_fifo() -> None:
    from duckclaw.graphs.on_the_fly_commands import (
        pop_all_fly_outbound_charts,
        pop_all_fly_outbound_charts_b64,
        register_fly_outbound_chart_b64,
    )

    sid = "admin-conv-test-fly-charts"
    register_fly_outbound_chart_b64(sid, "chart-a", chart_name="20260608_sesion_pnl.png")
    register_fly_outbound_chart_b64(sid, "chart-b", chart_name="20260608_sesion_participacion.png")
    popped = pop_all_fly_outbound_charts_b64(sid)
    assert popped == ["chart-a", "chart-b"]
    assert pop_all_fly_outbound_charts_b64(sid) == []

    sid2 = "admin-conv-test-fly-charts-names"
    register_fly_outbound_chart_b64(sid2, "chart-a", chart_name="a.png")
    register_fly_outbound_chart_b64(sid2, "chart-b")
    b64s, names = pop_all_fly_outbound_charts(sid2)
    assert b64s == ["chart-a", "chart-b"]
    assert names == ["a.png", "chart-2.png"]


def test_admin_visual_fields_from_fly_charts() -> None:
    from main import _admin_visual_fields_from_invoke_result

    result = {
        "response": "status ok",
        "figure_base64": "pnl-b64",
        "fly_charts_b64": ["pnl-b64", "pie-b64"],
    }
    out = _admin_visual_fields_from_invoke_result("admin-playground", result, "default")
    assert out.get("figure_base64") == "pnl-b64"
    assert out.get("fly_charts_b64") == ["pnl-b64", "pie-b64"]

    empty = _admin_visual_fields_from_invoke_result("123456789", result, "default")
    assert empty == {}


def test_admin_visual_fields_fly_chart_artifact_ids() -> None:
    from main import _admin_visual_fields_from_invoke_result

    result = {
        "response": "status ok",
        "fly_chart_artifact_ids": ["aaa-bbb", "ccc-ddd"],
        "fly_chart_names": ["20260608_sesion_pnl.png", "20260608_sesion_participacion.png"],
    }
    out = _admin_visual_fields_from_invoke_result("admin-conv-abc", result, "default")
    assert out.get("fly_chart_artifact_ids") == ["aaa-bbb", "ccc-ddd"]
    assert out.get("fly_chart_names") == [
        "20260608_sesion_pnl.png",
        "20260608_sesion_participacion.png",
    ]
    assert out.get("artifact_id") == "aaa-bbb"
    assert out.get("artifact_tenant_id") == "default"


def test_embed_visual_artifact_markers_for_history() -> None:
    from core.chat_visual_artifacts import embed_visual_artifact_markers_for_history

    out = embed_visual_artifact_markers_for_history(
        "Report ready",
        {
            "fly_chart_artifact_ids": [
                "440754b9-d489-40cc-872f-4938faf89768",
                "2ab40842-bc48-4497-a79a-60f54f92ddf0",
            ],
            "fly_chart_names": ["chart_a.png", "chart_b.png"],
        },
    )
    assert "visual_artifact_id: 440754b9-d489-40cc-872f-4938faf89768" in out
    assert "visual_artifact_id: 2ab40842-bc48-4497-a79a-60f54f92ddf0" in out
    assert "Report ready" in out


def test_persist_admin_fly_charts_writes_png(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from main import _persist_admin_fly_charts

    import base64

    png = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 32).decode("ascii")

    def _fake_dir(tenant_id: str) -> Path:
        d = tmp_path / tenant_id / "artifacts"
        d.mkdir(parents=True)
        return d

    monkeypatch.setattr(
        "duckclaw.forge.skills.comfyui_bridge.tenant_artifacts_dir",
        _fake_dir,
    )
    ids = _persist_admin_fly_charts("default", [png, png])
    assert len(ids) == 2
    for aid in ids:
        assert (tmp_path / "default" / "artifacts" / f"{aid}.png").is_file()


def test_admin_visual_fields_single_chart_no_list() -> None:
    from main import _admin_visual_fields_from_invoke_result

    result = {"figure_base64": "only-one"}
    out = _admin_visual_fields_from_invoke_result("admin-conv-abc", result, "default")
    assert out.get("figure_base64") == "only-one"
    assert "fly_charts_b64" not in out
