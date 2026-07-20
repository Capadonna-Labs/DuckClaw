from __future__ import annotations

from duckclaw.ops.stack_deploy import HEARTBEAT_NAME, INDEXER_NAME, stack_deploy_shell


def test_stack_deploy_shell_includes_indexer_heartbeat_and_recycle() -> None:
    script = stack_deploy_shell(repo_root="/tmp/duckclaw")
    assert INDEXER_NAME in script
    assert HEARTBEAT_NAME in script
    assert "DuckClaw-Gateway" in script
    assert "DuckClaw-DB-Writer" in script
    assert "pm2 delete" in script
    assert "STACK_DEPLOY_OK" in script


def test_run_stack_deploy_full_calls_offline_post(monkeypatch, tmp_path) -> None:
    from duckclaw.ops import stack_deploy as mod

    (tmp_path / ".env").write_text("X=1\n", encoding="utf-8")
    calls: list[str] = []

    monkeypatch.setattr(mod, "run_uv_sync", lambda **_k: True)
    monkeypatch.setattr(mod, "run_pm2_stop_stack", lambda **_k: True)
    monkeypatch.setattr(mod, "run_migrate", lambda **_k: True)
    monkeypatch.setattr(mod, "_wait_gateway_health", lambda *_a, **_k: True)
    monkeypatch.setattr(mod, "_pm2_status", lambda _n: "online")
    monkeypatch.setattr(
        mod.subprocess,
        "run",
        lambda *_a, **_k: type("P", (), {"returncode": 0})(),
    )

    def _post(*, print_fn, mirror: bool) -> None:
        calls.append(f"mirror={mirror}")
        print_fn("post")

    monkeypatch.setattr(mod, "_run_framework_offline_post_deploy", _post)
    code = mod.run_stack_deploy(repo_root=tmp_path, print_fn=calls.append, full=True)
    assert code == 0
    assert any(c == "mirror=True" for c in calls)
