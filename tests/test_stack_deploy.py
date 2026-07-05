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
