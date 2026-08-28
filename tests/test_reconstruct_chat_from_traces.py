from __future__ import annotations

import json
from pathlib import Path


def test_reconstruct_chat_messages_from_traces(tmp_path: Path, monkeypatch):
    from duckclaw.graphs import conversation_traces as ct

    monkeypatch.setattr(ct, "get_conversation_traces_dir", lambda: tmp_path)
    day = tmp_path / "2026" / "08" / "18"
    day.mkdir(parents=True)
    sid = "admin-conv-abc"
    lines = [
        {
            "session_id": sid,
            "timestamp": "2026-08-18T10:00:00Z",
            "messages": [
                {"role": "system", "content": "soul"},
                {"role": "user", "content": "[KNOWLEDGE_SCOPE]\nX\n[/KNOWLEDGE_SCOPE]\n\n/loop --now"},
                {"role": "assistant", "content": "ok1"},
            ],
        },
        {
            "session_id": sid,
            "timestamp": "2026-08-18T10:01:00Z",
            "messages": [
                {"role": "user", "content": "status"},
                {"role": "assistant", "content": "paper"},
            ],
        },
        {
            "session_id": "admin-conv-other",
            "timestamp": "2026-08-18T10:02:00Z",
            "messages": [{"role": "user", "content": "nope"}],
        },
    ]
    (day / "traces.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    out = ct.reconstruct_chat_messages_from_traces(sid)
    assert [m["role"] for m in out] == ["user", "assistant", "user", "assistant"]
    assert out[0]["content"] == "/loop --now"
    assert out[3]["content"] == "paper"
