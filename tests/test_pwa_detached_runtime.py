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
    assert "if (detachedRunning || reconciledFromHistory)" in turn
    assert "applyCompletedTurnFromHistory" in turn
    assert "setLoading(false);" in turn
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
    assert "forceRelease" in resume
    assert "localStorage.setItem(key(turn.chatId)" in state


def test_history_reload_restores_tool_usage_from_activity_backlog() -> None:
    history = (
        ROOT / "apps/duckclaw-admin/src/components/chat/useAdminChatHistory.ts"
    ).read_text(encoding="utf-8")
    shared = (
        ROOT / "apps/duckclaw-admin/src/lib/chatActivityHeartbeats.ts"
    ).read_text(encoding="utf-8")

    assert "toolHeartbeatsFromActivity" in history
    assert "from '@/lib/chatActivityHeartbeats'" in history
    assert "export function toolHeartbeatsFromActivity(" in shared
    assert "getPlaygroundChatActivity(chatId, 80)" in history
    assert "activityEphemeral" in history
    assert "mergeEphemeralHeartbeats(" in history


def test_detached_completion_keeps_tool_usage_from_activity_backlog() -> None:
    turn = (
        ROOT / "apps/duckclaw-admin/src/components/chat/runAdminChatTurn.ts"
    ).read_text(encoding="utf-8")

    assert "toolHeartbeatsFromActivity" in turn
    assert "from '@/lib/chatActivityHeartbeats'" in turn
    assert "applyCompletedTurnFromHistory" in turn
    assert "getPlaygroundChatActivity(chatId, 80)" in turn
    assert "mergeEphemeralHeartbeats(" in turn
    assert "startLiveHistoryWatchdog" in turn


def test_tool_usage_timer_stays_live_during_detached_loading() -> None:
    group = (
        ROOT / "apps/duckclaw-admin/src/components/chat/ToolUsageGroup.tsx"
    ).read_text(encoding="utf-8")
    message_list = (
        ROOT / "apps/duckclaw-admin/src/components/chat/AdminChatMessageList.tsx"
    ).read_text(encoding="utf-8")

    assert "liveWhileLoading?: boolean" in group
    assert "const headerRunning = anyRunning || liveWhileLoading" in group
    assert "liveWhileLoading={" in message_list
    assert "toolGroupHasRunning(messages, item.indices)" in message_list
    # No cronómetro eterno solo por loading=true sin tools/streaming.
    assert "msg.streaming" in message_list


def test_sse_idle_timeout_and_idle_error_helpers() -> None:
    sse = (ROOT / "apps/duckclaw-admin/src/lib/sseChat.ts").read_text(encoding="utf-8")
    idle = (ROOT / "apps/duckclaw-admin/src/lib/sseIdle.ts").read_text(encoding="utf-8")
    api = (ROOT / "apps/duckclaw-admin/src/services/admin/chatApi.ts").read_text(encoding="utf-8")

    assert "SseIdleTimeoutError" in sse
    assert "SSE_IDLE_TIMEOUT_MS" in idle
    assert "isSseIdleTimeoutError" in api
    assert "readWithIdleTimeout" in sse
