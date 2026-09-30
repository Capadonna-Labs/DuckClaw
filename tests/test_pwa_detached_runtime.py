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
    assert "beginDetachedPollEpoch()" in turn
    assert "pollDetachedActivity(epoch)" in turn
    assert "pollDetachedCompletion(epoch)" in turn
    assert "if (epoch !== detachedPollEpoch) return" in turn
    assert "if (detachedRunning)" in turn
    assert "setLoading(false);" in turn.split("if (detachedRunning)", 1)[1]
    assert "preserveInFlightOptimisticTurn(" in turn
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
    assert "preserveInFlightOptimisticTurn(" in resume
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

    completion = turn.split("const pollDetachedCompletion = (epoch: number) =>", 1)[1]
    assert "function toolHeartbeatsFromActivity(" in turn
    assert "getPlaygroundChatActivity(chatId, 80)" in completion
    assert "activityEphemeral" in completion
    assert "mergeEphemeralHeartbeats(" in completion
    assert "preserveInFlightOptimisticTurn(" in completion


def test_tool_usage_clock_runs_until_turn_end() -> None:
    """Header clock ticks for the whole in-flight turn and freezes when it ends.

    The earlier ~30m inflation came from detached turns whose ``loading`` never
    cleared (completion was inferred from history and misfired); detached
    completion now keys on the gateway's turn_done marker, so the clock stops
    with the turn instead of only while a tool runs.
    """
    group = (
        ROOT / "apps/duckclaw-admin/src/components/chat/ToolUsageGroup.tsx"
    ).read_text(encoding="utf-8")
    message_list = (
        ROOT / "apps/duckclaw-admin/src/components/chat/AdminChatMessageList.tsx"
    ).read_text(encoding="utf-8")
    turn = (
        ROOT / "apps/duckclaw-admin/src/components/chat/runAdminChatTurn.ts"
    ).read_text(encoding="utf-8")

    assert "liveWhileLoading?: boolean" in group
    assert "(anyRunning || liveWhileLoading) && blockStartedAt != null" in group
    assert "liveWhileLoading={loading && itemIdx === liveToolGroupIdx}" in message_list
    completion = turn.split("const pollDetachedCompletion = (epoch: number) =>", 1)[1]
    assert "ev.kind === 'turn_done'" in completion
    # History must be read AFTER seeing turn_done, or a pre-reply history can be
    # paired with the end marker and the final answer never shows.
    assert completion.index("getPlaygroundChatActivity(") < completion.index("getConversation(")


def test_detached_polls_outlive_long_turns_and_never_stay_stuck() -> None:
    """Sandbox turns run 15-20+ min: polling must keep going until turn_done and,
    at the cap, finalize from history instead of leaving loading on forever."""
    turn = (ROOT / "apps/duckclaw-admin/src/components/chat/runAdminChatTurn.ts").read_text(encoding="utf-8")
    resume = (ROOT / "apps/duckclaw-admin/src/components/chat/useDetachedTurnResume.ts").read_text(encoding="utf-8")
    assert "const DETACHED_POLL_MAX_MS = 60 * 60_000;" in turn
    assert "lastRound" in turn.split("const pollDetachedCompletion", 1)[1]
    assert "const DETACHED_RESUME_MAX_MS = 60 * 60_000;" in resume
    assert "600_000" not in resume  # old fixed schedule: last check at 10 min
    assert "void finishWithHistory()" in resume


def test_detached_turn_resets_backlog_and_marks_turn_done() -> None:
    route = (
        ROOT / "services/api-gateway/routers/admin_domains/playground/chat_routes.py"
    ).read_text(encoding="utf-8")
    detached = route.split("if body.detached", 1)[1]
    # Reset must happen before the turn is accepted (no poll can see the previous turn).
    assert detached.index("reset_admin_heartbeat_backlog") < detached.index('"accepted": True')
    assert "kind=TURN_DONE_KIND" in detached
