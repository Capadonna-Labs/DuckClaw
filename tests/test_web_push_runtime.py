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
    assert "pwa-presence" not in service_worker                     # no presence reporting: the switch decides, not what is on screen


def test_push_is_decided_by_the_notifications_switch_not_by_pwa_visibility() -> None:
    from duckclaw.web_push import _subscription_from_row

    sw = (ROOT / "apps/duckclaw-admin/public/sw.js").read_text(encoding="utf-8")
    pwa = (ROOT / "apps/duckclaw-admin/src/components/shared/PwaServiceWorker.tsx").read_text(encoding="utf-8")
    client = (ROOT / "apps/duckclaw-admin/src/lib/webPushClient.ts").read_text(encoding="utf-8")
    toggles = (ROOT / "apps/duckclaw-admin/src/components/playground/usePlaygroundChatToggles.ts").read_text(encoding="utf-8")
    gateway_notifications = (ROOT / "services/api-gateway/routers/admin_domains/notifications.py").read_text(encoding="utf-8")
    suggestions = (ROOT / "services/api-gateway/routers/admin_domains/chat_suggestions.py").read_text(encoding="utf-8")
    chat_turn = (ROOT / "services/api-gateway/routers/admin_domains/playground/chat_turn.py").read_text(encoding="utf-8")
    heartbeat = (ROOT / "services/heartbeat/main.py").read_text(encoding="utf-8")
    bff = (ROOT / "apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts").read_text(encoding="utf-8")

    for gone in ("pwa_visible", "pwa-presence", "pwa_presence", "reportPwaPresence"):
        assert gone not in (gateway_notifications + chat_turn + heartbeat + bff + pwa + sw), gone
    assert "visibilityState" not in sw and "matchAll" not in sw           # the worker no longer asks whether a window is open
    assert "showNotification(title, options)" in sw                      # a delivered push is always shown (a silent push can get the subscription revoked)
    assert "enabled: bool = True" in gateway_notifications and '"enabled": body.enabled' in gateway_notifications
    assert "ensureWebPushSubscription(false)" in toggles and "enabled," in client and "if (!enabled && !existing) return false" in client
    assert "send_web_push_notifications" not in suggestions               # suggestions never push (iOS cannot reply from a third-party watch)
    base = {"subscription": {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x" * 20, "auth": "y" * 10}}}
    assert _subscription_from_row({"value_json": base}) is not None                       # rows saved before the switch existed stay on
    assert _subscription_from_row({"value_json": {**base, "enabled": True}}) is not None
    assert _subscription_from_row({"value_json": {**base, "enabled": False}}) is None     # the device switched Notificaciones off


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
    # The SSE path takes the reply from the final "done" event; without it every push said "Turno completado."
    assert 'json.loads(chunk.removeprefix("data: ")' in chat_turn


def _push_parts():
    import re

    src = (ROOT / "services/api-gateway/routers/admin_domains/playground/chat_turn.py").read_text(encoding="utf-8")
    block = src[src.index("_PUSH_MD = "):src.index("async def _suggestion_selected_prefix")]
    ns: dict = {"re": re}
    exec(block, ns)  # noqa: S102 - the helper block of our own source
    return ns["_playground_push_parts"]


def test_push_title_is_the_headline_and_body_up_to_three_bullets() -> None:
    parts = _push_parts()
    reply = (
        "## Resumen del portafolio\n\n"
        "| Ticker | Peso |\n|---|---|\n| SPY | 10% |\n\n"
        "- **SPY** pesa 10% y está dentro de banda\n- Sin órdenes de rebalanceo hoy\n- FOMC mañana: ventana sin compras\n- Cuarto punto que no cabe\n"
    )
    title, body = parts(reply, "quant_analyst")
    assert title == "Resumen del portafolio"
    assert body.splitlines() == ["• SPY pesa 10% y está dentro de banda", "• Sin órdenes de rebalanceo hoy", "• FOMC mañana: ventana sin compras"]
    # a "Veredicto:" line wins as title, like the proactive pushes
    title, _ = parts("Contexto largo.\nVeredicto: 2 órdenes por revisar\n- uno\n- dos", "w")
    assert title == "2 órdenes por revisar"
    # prose without bullets: the first sentence is the title, the next ones the bullets
    title, body = parts("El mercado cerró mixto. SPY subió 0,4%. El VIX bajó a 15.", "w")
    assert title == "El mercado cerró mixto." and body == "• SPY subió 0,4%.\n• El VIX bajó a 15."
    assert parts("", "quant_analyst") == ("DuckClaw · quant_analyst", "Turno completado.")



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
