"""Tests for /loop --status (alignment + next-delta footer, no summarize)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from duckclaw.commands.loop import (
    _parse_loop_args,
    execute_loop,
    execute_loop_status_with_meta,
    is_loop_status_fly_text,
)
from duckclaw.homeostasis.goals_alignment import (
    AlignmentItem,
    AlignmentReport,
    format_alignment_report_markdown,
)


class _FakeDb:
    def __init__(self) -> None:
        self._rows: dict[str, str] = {}

    def execute(self, sql: str) -> None:
        if "INSERT INTO agent_config" in sql:
            parts = sql.split("VALUES ('", 1)[1]
            key, rest = parts.split("', '", 1)
            val = rest.split("')", 1)[0]
            self._rows[key] = val.replace("''", "'")


def test_parse_loop_args_status() -> None:
    assert _parse_loop_args("--status") == {"action": "status"}


def test_is_loop_status_fly_text() -> None:
    assert is_loop_status_fly_text("/loop --status")
    assert is_loop_status_fly_text("", "/loop --status")
    assert not is_loop_status_fly_text("/loop on --delta 15m")
    assert not is_loop_status_fly_text("/loop on")
    assert not is_loop_status_fly_text("/goals")


def test_parse_loop_args_status_rejects_mix_with_on() -> None:
    out = _parse_loop_args("on --status")
    assert "error" in out


def test_parse_loop_args_status_rejects_mix_with_delta() -> None:
    out = _parse_loop_args("--delta 3min --status")
    assert "error" in out


def test_format_alignment_report_markdown_empty() -> None:
    report = AlignmentReport(aligned=True, misaligned_count=0, goals_count=0)
    text = format_alignment_report_markdown(report)
    assert "## Alineación con /goals" in text
    assert "/goals" in text


def test_format_alignment_report_markdown_anomaly() -> None:
    report = AlignmentReport(
        aligned=False,
        misaligned_count=1,
        goals_count=1,
        items=[
            AlignmentItem(
                belief_key="error_rate_pct",
                title="Tasa de error baja",
                target=2.0,
                observed=5.0,
                threshold=0.5,
                delta=3.0,
                is_anomaly=True,
                has_data=True,
                goal_kind="monitor",
            )
        ],
    )
    text = format_alignment_report_markdown(report)
    assert "desvío" in text
    assert "Tasa de error baja" in text
    assert "monitor" in text


@patch("duckclaw.homeostasis.goals_alignment.assess_goals_alignment")
def test_execute_loop_status_with_meta_includes_footer_no_summarize(
    mock_assess: MagicMock,
) -> None:
    mock_assess.return_value = AlignmentReport(
        aligned=True,
        misaligned_count=0,
        goals_count=1,
        items=[
            AlignmentItem(
                belief_key="g1",
                title="Meta test",
                target=1.0,
                observed=1.0,
                threshold=0.1,
                delta=0.0,
                is_anomaly=False,
                has_data=True,
            )
        ],
    )
    db = _FakeDb()
    reply, meta = execute_loop_status_with_meta(db, "chat-1", "--status", tenant_id="default")
    assert "✅ Estado /loop" in reply
    assert "## Alineación con /goals" in reply
    assert "## Resumen del hilo" not in reply
    assert "Próximo ciclo" in reply or "Modo /loop" in reply or "inactivo" in reply.lower()
    assert meta == {}


def test_execute_loop_routes_status(mock_manifest: None) -> None:
    db = _FakeDb()
    with patch("duckclaw.commands.loop.execute_loop_status", return_value="status-ok") as mock_status:
        out = execute_loop(db, "1", "--status", tenant_id="default")
    assert out == "status-ok"
    mock_status.assert_called_once()


def test_fly_dispatch_loop_status_does_not_start_cycle() -> None:
    from duckclaw.commands.fly_dispatch import _dispatch_fly_command

    db = MagicMock()
    with patch(
        "duckclaw.commands.fly_dispatch.execute_loop_status",
        return_value="✅ Estado /loop",
    ) as mock_status:
        with patch("duckclaw.commands.fly_dispatch.execute_loop_immediate") as mock_immediate:
            out = _dispatch_fly_command(db, "chat-1", "loop", "--status", tenant_id="t1")
    assert out == "✅ Estado /loop"
    mock_status.assert_called_once()
    mock_immediate.assert_not_called()


@pytest.fixture
def mock_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Manifest:
        goals = []

    def _load(*_a: object, **_k: object) -> _Manifest:
        return _Manifest()

    monkeypatch.setattr("harness_core.targets.load_homeostasis_manifest", _load)
    monkeypatch.setattr(
        "duckclaw.commands.loop.get_loop_chat_state",
        lambda _db, _cid, key: "180" if key == "loop_delta_seconds" else "",
    )
    monkeypatch.setattr("duckclaw.commands.loop.is_loop_delta_idle_mode", lambda *_a, **_k: True)
    monkeypatch.setattr("duckclaw.commands.loop.get_loop_last_activity_epoch", lambda *_a, **_k: 0.0)
