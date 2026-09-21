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
    assert "mergeHistoryWithEphemeral(withImages, ephemeral)" in turn
    assert "readEphemeralHeartbeats(chatId, activeWorker)" in turn
    assert "writePendingDetachedTurn({" in turn
    assert "clearPendingDetachedTurn(chatId)" in turn


def test_pwa_reopens_resume_detached_turn_from_activity() -> None:
    hook = (
        ROOT / "apps/duckclaw-admin/src/components/chat/useAdminChat.ts"
    ).read_text(encoding="utf-8")
    resume = (
        ROOT / "apps/duckclaw-admin/src/components/chat/useDetachedTurnResume.ts"
    ).read_text(encoding="utf-8")
    state = (
        ROOT / "apps/duckclaw-admin/src/lib/detachedTurnState.ts"
    ).read_text(encoding="utf-8")

    assert "useDetachedTurnResume" in hook
    assert "from './useDetachedTurnResume'" in hook
    assert "readPendingDetachedTurn(chatId)" in resume
    assert "getPlaygroundChatActivity(chatId, 80)" in resume
    assert "setLoading(true)" in resume
    assert "mergeHistoryWithEphemeral(withImages, ephemeral)" in resume
    assert "clearPendingDetachedTurn(chatId)" in resume
    assert "localStorage.setItem(key(turn.chatId)" in state


def test_history_reload_restores_tool_usage_from_activity_backlog() -> None:
    history = (
        ROOT / "apps/duckclaw-admin/src/components/chat/useAdminChatHistory.ts"
    ).read_text(encoding="utf-8")

    assert "function toolHeartbeatsFromActivity(" in history
    assert "getPlaygroundChatActivity(chatId, 80)" in history
    assert "activityEphemeral" in history
    assert "mergeEphemeralHeartbeats(" in history
    assert "turnUserIndex" in history


def test_detached_completion_keeps_tool_usage_from_activity_backlog() -> None:
    turn = (
        ROOT / "apps/duckclaw-admin/src/components/chat/runAdminChatTurn.ts"
    ).read_text(encoding="utf-8")

    completion = turn.split("const pollDetachedCompletion = () =>", 1)[1]
    assert "function toolHeartbeatsFromActivity(" in turn
    assert "getPlaygroundChatActivity(chatId, 80)" in completion
    assert "activityEphemeral" in completion
    assert "mergeEphemeralHeartbeats(" in completion


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
