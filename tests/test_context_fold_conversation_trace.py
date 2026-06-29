"""Trazas JSONL para /summarize (context fold)."""

from __future__ import annotations

import json
from pathlib import Path

from duckclaw.graphs.conversation_traces import append_context_fold_conversation_trace


def test_append_context_fold_conversation_trace_sft(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DUCKCLAW_CONVERSATION_TRACES_DIR", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_CONVERSATION_TRACES_FORMAT", "sft")
    monkeypatch.setenv("DUCKCLAW_SAVE_CONVERSATION_TRACES", "true")

    append_context_fold_conversation_trace(
        "chat-fold-trace-1",
        "/summarize",
        "✅ Hilo compactado manualmente.\nResumen guardado (120 caracteres).",
        worker_id="worker-a",
        elapsed_ms=42,
        status="SUCCESS",
        context_estimated_tokens=8500,
        messages_before=48,
        kept_history=[{"role": "user", "content": "ultimo"}],
        summary_chars=120,
        vault_saved=True,
    )

    files = list(tmp_path.rglob("traces.jsonl"))
    assert len(files) == 1
    record = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert record["event"] == "context_fold"
    assert record["worker_id"] == "worker-a"
    assert record["session_id"] == "chat-fold-trace-1"
    assert record["messages"][0]["content"] == "/summarize"
    assert "compactado" in record["messages"][1]["content"]
    fold = record["context_fold"]
    assert fold["command"] == "/summarize"
    assert fold["context_estimated_tokens"] == 8500
    assert fold["messages_before"] == 48
    assert fold["messages_after"] == 1
    assert fold["summary_chars"] == 120
    assert fold["vault_saved"] is True


def test_append_context_fold_skipped_when_traces_disabled(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DUCKCLAW_CONVERSATION_TRACES_DIR", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_SAVE_CONVERSATION_TRACES", "false")

    append_context_fold_conversation_trace(
        "chat-fold-trace-2",
        "/summarize",
        "ok",
        worker_id="default",
    )

    assert list(tmp_path.rglob("traces.jsonl")) == []
