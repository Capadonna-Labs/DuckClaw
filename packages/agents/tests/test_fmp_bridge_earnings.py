"""FMP earnings calendar + transcript (formato estable), sin llamada HTTP real."""

from __future__ import annotations

import pytest

from duckclaw.forge.skills import fmp_bridge as fb


@pytest.fixture(autouse=True)
def _noop_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test_dummy_key")


def test_earnings_calendar_range_validation() -> None:
    msg = fb._get_fmp_earnings_calendar_impl("2026-01-01", "2026-06-01", limit=50)
    assert "superar 90 días" in msg


def test_earnings_calendar_format(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fb,
        "_fmp_get_json",
        lambda path, q: [
            {"symbol": "NVDA", "date": "2026-06-03", "epsEstimated": "0.76", "time": "amc"},
            {"symbol": "AAPL", "date": "2026-06-02", "eps": "1.2"},
        ]
        if "earnings-calendar" in path
        else [],
    )

    out = fb._get_fmp_earnings_calendar_impl("2026-06-01", "2026-06-07", limit=50)
    assert "Calendario earnings FMP" in out
    assert "NVDA" in out
    assert "AAPL" in out


@pytest.mark.parametrize(
    ("data", "snippet"),
    [
        ([{"content": "Hello guidance risk"}], ""),
        ([], "lista vacía"),
        ([{}], "sin campo"),
    ],
)
def test_extract_transcript_body(data: object, snippet: str) -> None:
    body, note = fb._extract_transcript_body(data)
    if snippet:
        assert snippet in note
        assert not body
    else:
        assert body == "Hello guidance risk"


def test_transcript_via_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fb,
        "_fmp_get_json",
        lambda path, q: [{"content": "We see margin pressure macro headwinds Q&A Operator: next question"}
        ]
        if "earning-call-transcript" in path
        else [],
    )

    raw = fb._get_fmp_earnings_transcript_impl("META", 2025, 1)
    assert "META" in raw
    assert "margin pressure macro" in raw
