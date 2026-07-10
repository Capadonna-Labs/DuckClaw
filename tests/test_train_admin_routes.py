"""Admin train routes — conversation trace lakes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_train_status_lists_conversation_traces(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    lake = tmp_path / "conversation_traces" / "2026" / "07" / "04"
    lake.mkdir(parents=True)
    trace_file = lake / "traces.jsonl"
    trace_file.write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "hola"},
                    {"role": "assistant", "content": "mundo"},
                ],
                "session_id": "s1",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_CONVERSATION_TRACES_DIR", str(tmp_path / "conversation_traces"))

    headers = {"X-Admin-Key": "test-admin-key"}
    r = admin_client.get("/api/v1/admin/train/status", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["conversation_traces"]["file_count"] >= 1
    assert data["conversation_traces"]["recent"][0]["line_count"] == 1


def test_train_trace_sample_returns_preview(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    root = tmp_path / "conversation_traces"
    rel_dir = root / "2026" / "07" / "04"
    rel_dir.mkdir(parents=True)
    (rel_dir / "traces.jsonl").write_text(
        json.dumps(
            {
                "messages": [
                    {"role": "user", "content": "pregunta"},
                    {"role": "assistant", "content": "respuesta"},
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_CONVERSATION_TRACES_DIR", str(root))

    headers = {"X-Admin-Key": "test-admin-key"}
    r = admin_client.get(
        "/api/v1/admin/train/traces/sample",
        headers=headers,
        params={"lake": "conversation_traces", "relative_path": "2026/07/04/traces.jsonl", "limit": 3},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total_lines_estimate"] == 1
    assert body["samples"][0]["instruction"] == "pregunta"
    assert body["samples"][0]["response"] == "respuesta"
