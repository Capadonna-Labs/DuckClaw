"""Tests SLM eval bridge and model approval HITL."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from duckclaw.forge.skills.slm_eval_bridge import _execute_slm_impl, register_slm_eval_skill
from duckclaw.hitl.model_approval_service import approve_model_adapter, request_model_approval


def test_request_and_approve_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pending = tmp_path / "db" / "private" / "slm_model_approvals_pending.json"
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    raw = request_model_approval(adapter_path="adapters/test_v1", summary="passed 5 exams")
    data = json.loads(raw)
    assert data["ok"] is True
    assert data["status"] == "pending"
    assert pending.is_file()

    result = approve_model_adapter(adapter_path="adapters/test_v1", chat_id="chat-1")
    assert result["ok"] is True
    assert "pm2 restart MLX-Inference" in result["message"]


def test_execute_slm_blocked_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Db:
        schema = "main"

    monkeypatch.setattr(
        "duckclaw.forge.skills.slm_eval_bridge.is_slm_enabled_for_chat",
        lambda db, cid, tenant_id="default": False,
    )
    out = _execute_slm_impl("prompt", chat_id="conv-1", db=_Db())
    assert "no habilitado" in out.lower()


def test_register_slm_eval_skill_adds_tools() -> None:
    tools: list = []
    register_slm_eval_skill(tools, {})
    names = {getattr(t, "name", "") for t in tools}
    assert "execute_slm" in names
    assert "record_slm_eval_lesson" in names
    assert "request_model_approval" in names
