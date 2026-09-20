from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_playground_chat_supports_detached_pwa_turns() -> None:
    schemas = (
        ROOT / "services/api-gateway/routers/admin_domains/playground/schemas.py"
    ).read_text(encoding="utf-8")
    route = (
        ROOT / "services/api-gateway/routers/admin_domains/playground/chat_routes.py"
    ).read_text(encoding="utf-8")

    assert "detached: bool" in schemas
    assert "if body.detached" in route
    assert "spawn_background(_run_detached())" in route
    assert '"accepted": True' in route


def test_ios_pwa_turn_uses_detached_mode_and_keeps_runtime_visible() -> None:
    turn = (
        ROOT / "apps/duckclaw-admin/src/components/chat/runAdminChatTurn.ts"
    ).read_text(encoding="utf-8")

    assert "detached: true" in turn
    assert "pollDetachedActivity()" in turn
    assert "pollDetachedCompletion()" in turn
    assert "if (detachedRunning)" in turn
    assert "setLoading(false);" in turn.split("if (detachedRunning)", 1)[1]


def test_tool_usage_timer_stays_live_during_detached_loading() -> None:
    group = (
        ROOT / "apps/duckclaw-admin/src/components/chat/ToolUsageGroup.tsx"
    ).read_text(encoding="utf-8")
    message_list = (
        ROOT / "apps/duckclaw-admin/src/components/chat/AdminChatMessageList.tsx"
    ).read_text(encoding="utf-8")

    assert "liveWhileLoading?: boolean" in group
    assert "const headerRunning = anyRunning || liveWhileLoading" in group
    assert "liveWhileLoading={loading && itemIdx === displayItems.length - 1}" in message_list
