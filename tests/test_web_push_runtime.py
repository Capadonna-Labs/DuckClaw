from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_gateway_notifications_router_registered() -> None:
    admin_router = (ROOT / "services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    assert "routers.admin_domains.notifications" in admin_router
    assert "router.include_router(notifications_router)" in admin_router


def test_web_push_subscription_uses_db_writer_runtime_setting() -> None:
    route = (ROOT / "services/api-gateway/routers/admin_domains/notifications.py").read_text(encoding="utf-8")
    assert "UpsertRuntimeSettingCommand" in route
    assert 'domain="web_push"' in route
    assert 'value_kind="json"' in route
    assert "enqueue_typed_command" in route


def test_heartbeat_attempts_web_push_for_proactive_ticks() -> None:
    heartbeat = (ROOT / "services/heartbeat/main.py").read_text(encoding="utf-8")
    assert "async def _send_web_push_notification" in heartbeat
    assert "list_web_push_subscriptions" in heartbeat
    assert "duckclaw-goals-" in heartbeat
    assert "duckclaw-loop-" in heartbeat
    assert "duckclaw-anomaly-" in heartbeat


def test_admin_registers_push_subscription_after_permission() -> None:
    client = (ROOT / "apps/duckclaw-admin/src/lib/webPushClient.ts").read_text(encoding="utf-8")
    notifications = (ROOT / "apps/duckclaw-admin/src/lib/chatNotifications.ts").read_text(encoding="utf-8")
    service_worker = (ROOT / "apps/duckclaw-admin/src/components/shared/PwaServiceWorker.tsx").read_text(
        encoding="utf-8"
    )
    assert "/api/admin/notifications/web-push/public-key" in client
    assert "/api/admin/notifications/web-push/subscriptions" in client
    assert "ensureWebPushSubscription" in notifications
    assert "Notification.permission === 'granted'" in service_worker
    assert "/api/admin/notifications/pwa-presence" in service_worker


def test_notifications_only_show_when_pwa_not_visible() -> None:
    service_worker = (ROOT / "apps/duckclaw-admin/public/sw.js").read_text(encoding="utf-8")
    pwa = (ROOT / "apps/duckclaw-admin/src/components/shared/PwaServiceWorker.tsx").read_text(
        encoding="utf-8"
    )
    unread = (
        ROOT / "apps/duckclaw-admin/src/components/chat/useFloatingChatUnread.ts"
    ).read_text(encoding="utf-8")
    gateway_notifications = (
        ROOT / "services/api-gateway/routers/admin_domains/notifications.py"
    ).read_text(encoding="utf-8")
    suggestions = (
        ROOT / "services/api-gateway/routers/admin_domains/chat_suggestions.py"
    ).read_text(encoding="utf-8")
    chat_turn = (
        ROOT / "services/api-gateway/routers/admin_domains/playground/chat_turn.py"
    ).read_text(encoding="utf-8")
    heartbeat = (ROOT / "services/heartbeat/main.py").read_text(encoding="utf-8")

    assert "matchAll({ type: 'window', includeUncontrolled: true })" in service_worker
    assert "client.visibilityState === 'visible'" in service_worker
    assert "client.focused" not in service_worker
    assert "if (visible) return undefined" in service_worker
    assert "reportPwaPresence(visible())" in pwa
    assert 'PWA_VISIBLE_KEY = "duckclaw:admin:pwa_visible"' in gateway_notifications
    assert "async def pwa_visible_recently" in gateway_notifications
    # Suggestions no longer push (iOS cannot reply from a third-party watch; it doubled each alert).
    assert "send_web_push_notifications" not in suggestions
    assert "if await pwa_visible_recently(redis_client):" in chat_turn
    assert 'await r.exists("duckclaw:admin:pwa_visible")' in heartbeat
    assert "{ requireBackground: true }" in unread
    assert "const shouldNotify = tabHidden;" in unread

def test_vapid_generator_is_documented_and_available() -> None:
    script = ROOT / "scripts/generate_web_push_vapid.py"
    assert script.exists()
    assert "WEB_PUSH_VAPID_PUBLIC_KEY" in script.read_text(encoding="utf-8")
    docs = (ROOT / "docs/deploy/DOCKER_FULL_WINDOWS.md").read_text(encoding="utf-8")
    env_example = (ROOT / "deploy/docker/.env.example").read_text(encoding="utf-8")
    assert "scripts/generate_web_push_vapid.py" in docs
    assert "scripts/generate_web_push_vapid.py" in env_example


def test_playground_chat_turn_attempts_web_push_on_completion() -> None:
    chat_turn = (
        ROOT / "services/api-gateway/routers/admin_domains/playground/chat_turn.py"
    ).read_text(encoding="utf-8")
    assert "async def _notify_playground_turn_done" in chat_turn
    assert "list_web_push_subscriptions" in chat_turn
    assert "duckclaw-playground-" in chat_turn
    # Streaming (SSE) path must notify on stream end regardless of how it ends
    # (success, error, or client disconnect) — the whole point is being able to
    # leave the PWA and still get told when the turn finished.
    assert "_sse_body_with_push_notification" in chat_turn
    assert "finally:" in chat_turn
    # Non-streaming path notifies right after the result comes back, tied to a
    # real user reference so a suggestion-pick can be recognized and annotated.
    assert "extract_playground_reply(result)" in chat_turn
    assert "incoming_message=prepared.original_user_message" in chat_turn



def test_hub_reads_wait_out_a_db_writer_lock(monkeypatch) -> None:
    """A read during a DB-Writer write must wait for the lock, not fail: a failed read surfaced
    as "sin suscripciones" (dropped pushes) and "Worker not found" on 18-Oct."""
    import duckclaw.db_bridge as bridge

    calls = {"n": 0}

    def _connect(path, read_only=False):
        calls["n"] += 1
        if calls["n"] < 3:
            raise OSError('IO Error: Could not set lock on file "hub.duckdb": Conflicting lock is held')
        return ("conn", path, read_only)

    monkeypatch.setattr(bridge._duckdb, "connect", _connect)
    monkeypatch.setattr(bridge.time, "sleep", lambda _s: None)
    assert bridge.connect_with_lock_retry("hub.duckdb", read_only=True) == ("conn", "hub.duckdb", True)
    assert calls["n"] == 3

    def _other(path, read_only=False):
        raise OSError("IO Error: file is not a database")

    monkeypatch.setattr(bridge._duckdb, "connect", _other)
    try:
        bridge.connect_with_lock_retry("hub.duckdb", read_only=True)
    except OSError as exc:
        assert "not a database" in str(exc)  # non-lock errors are not retried
    else:
        raise AssertionError("expected the non-lock error")
