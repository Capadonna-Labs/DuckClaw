"""Tests /comfyui --provider command."""

from __future__ import annotations

from duckclaw.graphs.on_the_fly_commands import execute_comfyui_provider


class _MemDb:
    def __init__(self):
        self.store: dict[str, str] = {}

    def query(self, sql: str):
        import json
        for k, v in self.store.items():
            if k in sql:
                return json.dumps([{"value": v}])
        return json.dumps([])

    def execute(self, sql: str) -> None:
        if "INSERT" in sql.upper():
            parts = sql.split("VALUES")
            if len(parts) > 1:
                chunk = parts[1]
                if "'" in chunk:
                    vals = [x.strip().strip("'") for x in chunk.split(",")]
                    if len(vals) >= 2:
                        self.store[vals[0]] = vals[1]


def test_comfyui_provider_sets_fal(monkeypatch) -> None:
    monkeypatch.setenv("FAL_KEY", "k")
    db = _MemDb()
    msg = execute_comfyui_provider(db, "chat-x", "--provider fal")
    assert "fal" in msg.lower()