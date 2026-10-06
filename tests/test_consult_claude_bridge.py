"""consult_claude: opt-in registration, read-only command, daily cap, result parsing."""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

from duckclaw.forge.skills import consult_claude_bridge as cc
from duckclaw.workers.skill_tool_registry import DEFAULT_SKILL_TOOL_REGISTRY, _register_configured_skill_tools


def _registered(skill_configs: dict) -> list[str]:
    tools: list = []
    spec = SimpleNamespace(skill_configs=skill_configs)
    _register_configured_skill_tools(
        tools, spec, phase="post_llm", tool_surface="", incoming_hint="", context={"tenant_id": "t"}
    )
    return [t.name for t in tools]


def test_registration_is_explicit_opt_in() -> None:
    assert any(d.skill_name == "consult_claude" for d in DEFAULT_SKILL_TOOL_REGISTRY)
    assert "consult_claude" not in _registered({})
    assert "consult_claude" not in _registered({"consult_claude": {}})
    assert "consult_claude" in _registered({"consult_claude": {"enabled": True}})


def test_command_is_read_only_and_hides_secrets(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_CONSULT_CLAUDE_ADD_DIRS", "/srv/vertical")
    cmd = cc.build_claude_command("¿por qué?", "datos")
    allowed = cmd[cmd.index("--allowedTools") + 1 : cmd.index("--settings")]
    assert not any(t.startswith(("Edit", "Write", "NotebookEdit", "WebFetch")) or t == "Bash" for t in allowed)
    assert all(t in ("Read", "Grep", "Glob") or t.startswith("Bash(") for t in allowed)
    assert cmd[cmd.index("--permission-mode") + 1] == "dontAsk"
    deny = json.loads(cmd[cmd.index("--settings") + 1])["permissions"]["deny"]
    assert "Read(**/.env*)" in deny
    assert cmd[cmd.index("--add-dir") + 1] == "/srv/vertical"
    assert "--max-budget-usd" in cmd


def test_daily_cap_blocks_before_running(monkeypatch) -> None:
    monkeypatch.setattr(cc.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(cc, "_take_daily_slot", lambda _t: (False, 6, 5))
    called = []
    monkeypatch.setattr(cc.subprocess, "run", lambda *a, **k: called.append(1))
    out = json.loads(cc._consult_claude_impl("algo falla aquí", tenant_id="t"))
    assert out["ok"] is False and "Límite diario" in out["error"] and not called


def test_parses_result_and_cost(monkeypatch) -> None:
    monkeypatch.setattr(cc.shutil, "which", lambda _n: "/usr/bin/claude")
    monkeypatch.setattr(cc, "_take_daily_slot", lambda _t: (True, 1, 5))
    payload = {"result": "**Causa**: x", "total_cost_usd": 0.42, "is_error": False}
    monkeypatch.setattr(
        cc.subprocess,
        "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 0, stdout=json.dumps(payload), stderr=""),
    )
    out = json.loads(cc._consult_claude_impl("algo falla aquí", tenant_id="t"))
    assert out == {"ok": True, "diagnosis": "**Causa**: x", "cost_usd": 0.42, "consults_today": "1/5"}
