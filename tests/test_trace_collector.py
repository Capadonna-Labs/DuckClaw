"""Tests for duckclaw.traces.TraceCollector."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from duckclaw.traces.collector import TraceCollector, _FALLBACK_PATH


def test_collect_delegates_to_append_conversation_trace() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "respuesta"},
    ]
    collector = TraceCollector("session-1", worker_id="worker-a")
    with patch("duckclaw.graphs.conversation_traces.append_conversation_trace") as append:
        ok = collector.collect(messages, status="SUCCESS", elapsed_ms=120.0)
    assert ok is True
    append.assert_called_once()
    kwargs = append.call_args.kwargs
    assert kwargs["worker_id"] == "worker-a"
    assert kwargs["status"] == "SUCCESS"
    assert kwargs["elapsed_ms"] == 120
    assert kwargs["messages"] == messages


def test_collect_rejects_short_messages() -> None:
    collector = TraceCollector("s1")
    with pytest.raises(ValueError, match="at least 2"):
        collector.collect([{"role": "user", "content": "solo"}])


def test_tenant_id_alias_maps_to_session_id() -> None:
    collector = TraceCollector("", tenant_id="tenant-x", worker_id="w1")
    assert collector.session_id == "tenant-x"


def test_collect_uses_fallback_on_append_failure(tmp_path, monkeypatch) -> None:
    fallback = tmp_path / "temp_traces.jsonl"
    monkeypatch.setattr("duckclaw.traces.collector._FALLBACK_PATH", fallback)
    messages = [
        {"role": "user", "content": "u"},
        {"role": "assistant", "content": "a"},
    ]
    collector = TraceCollector("sess-fallback")
    with patch(
        "duckclaw.graphs.conversation_traces.append_conversation_trace",
        side_effect=OSError("disk full"),
    ):
        ok = collector.collect(messages, status="FAILED", elapsed_ms=1.0)
    assert ok is True
    lines = fallback.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert row["session_id"] == "sess-fallback"
    assert row["status"] == "FAILED"
    assert row["messages"] == messages


def test_trace_collector_module_has_no_redis_import() -> None:
    repo = Path(__file__).resolve().parents[1]
    collector_py = repo / "packages" / "agents" / "src" / "duckclaw" / "traces" / "collector.py"
    text = collector_py.read_text(encoding="utf-8")
    assert "import redis" not in text
    assert "from redis" not in text
    assert "db_write_queue" not in text
    assert "duckclaw.extensions" not in text
