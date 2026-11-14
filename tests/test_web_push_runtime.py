import pytest
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
    assert "setChatMuted(chatId, !next)" in toggles and "muted_tags: mutedTags" in client and "enabled: true" in client   # the switch is per chat, never the whole device
    assert "muted_tags" in gateway_notifications and "list_web_push_subscriptions, db_path, push_tag" in chat_turn and "list_web_push_subscriptions, db_path, tag" in heartbeat
    assert "send_web_push_notifications" not in suggestions               # suggestions never push (iOS cannot reply from a third-party watch)
    base = {"subscription": {"endpoint": "https://push.example/abc", "keys": {"p256dh": "x" * 20, "auth": "y" * 10}}}
    assert _subscription_from_row({"value_json": base}) is not None                       # rows saved before the switch existed stay on
    assert _subscription_from_row({"value_json": {**base, "enabled": True}}) is not None
    assert _subscription_from_row({"value_json": {**base, "enabled": False}}) is None     # the device switched Notificaciones off
    muted = {"value_json": {**base, "muted_tags": ["duckclaw-playground-a"]}}
    assert _subscription_from_row(muted, "duckclaw-playground-a") is None       # that chat is muted on this device
    assert _subscription_from_row(muted, "duckclaw-playground-b") is not None   # other chats still arrive
    assert _subscription_from_row(muted, "heartbeat-quant") is not None         # and so do the system alerts


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


def test_titles_over_30_characters_are_cut_and_moved_whole_to_the_body() -> None:
    from duckclaw.web_push import fit_title

    assert fit_title("Brent sube", "detalle") == ("Brent sube", "detalle")
    t, b = fit_title("Irán ofrece flexibilidad para reabrir Ormuz si EE. UU. levanta restricciones", "Brent 114,99")
    assert len(t) <= 30 and t.endswith("…") and " " not in t[-2:]
    assert b == "Irán ofrece flexibilidad para reabrir Ormuz si EE. UU. levanta restricciones\nBrent 114,99"
    t, b = fit_title("A" * 50, "")
    assert len(t) == 30 and b == "A" * 50                          # no word boundary: hard cut
    t, b = fit_title("ALTA · CVE-2026-109619 ya se explota (CISA)", "ALTA · CVE-2026-109619 ya se explota (CISA) plazo")
    assert b.startswith("ALTA · CVE-2026-109619") and b.count("CVE-2026-109619") == 1   # body already opens with the title


def test_push_log_is_readable_newest_first_and_filterable_by_tag() -> None:
    """A job's push is ephemeral on the device: /notifications/push-log is where its text can be read again (05-nov profit-taking)."""
    import sys

    import duckdb

    sys.path.insert(0, str(ROOT / "services/api-gateway"))
    from routers.admin_domains.notifications import load_push_log

    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE main.push_log (id VARCHAR, tenant_id VARCHAR, title VARCHAR, body VARCHAR, tag VARCHAR, url VARCHAR, sent INTEGER, failed INTEGER, error VARCHAR, created_at TIMESTAMP)")
    con.execute("INSERT INTO main.push_log VALUES ('a','t','viejo','b','quant-alert','/',1,0,'','2026-11-05 10:00:00'), ('b','t','nuevo','b2','otra','/',1,0,'','2026-11-05 16:10:00')")
    rows = load_push_log(con, 10)
    assert [r["title"] for r in rows] == ["nuevo", "viejo"] and rows[0]["created_at"].startswith("2026-11-05 16:10")
    assert [r["title"] for r in load_push_log(con, 10, "quant-alert")] == ["viejo"]
    assert load_push_log(con, 10, "x' OR '1'='1") == []


def _eval_row(suite: str, ts: str, **statuses: str) -> dict:
    import json

    return {"value_json": json.dumps({"suite": suite, "ts": ts, "model": "m", "cases": {c: {"status": s, "passes": 3 if s == "always_pass" else 0, "n": 3, "type": "t", "failures": []} for c, s in statuses.items()}})}


def test_evals_tab_summarizes_latest_run_history_and_regressions() -> None:
    import sys

    sys.path.insert(0, str(ROOT / "services/api-gateway"))
    from routers.admin_domains.evals import summarize

    rows = [_eval_row("quant", "2026-11-05T22:30:00Z", a="always_pass", b="always_fail", c="flaky"),
            _eval_row("quant", "2026-11-04T22:30:00Z", a="always_pass", b="always_pass", c="always_pass", d="always_pass"),
            _eval_row("other", "2026-11-05T01:00:00Z", x="always_pass"), {"value_json": "not json"}, {"value_json": '{"cases": {}}'}]
    got = {s["suite"]: s for s in summarize(rows)}
    q = got["quant"]
    assert q["latest"]["ts"] == "2026-11-05T22:30:00Z" and (q["latest"]["total"], q["latest"]["always_pass"], q["latest"]["flaky"], q["latest"]["always_fail"]) == (3, 1, 1, 1)
    assert q["regressed"] == ["b", "c", "d"] and [h["ts"][:10] for h in q["history"]] == ["2026-11-05", "2026-11-04"]
    assert got["other"]["regressed"] == [] and len(got) == 2
    assert q["requirements"] == []   # runs that declare none
    assert q["by_type"] == [{"type": "t", "passing": 1, "total": 3, "prev_passing": 4, "prev_total": 4}]


def test_evals_tab_flags_a_regression_on_an_edited_case() -> None:
    import json
    import sys

    sys.path.insert(0, str(ROOT / "services/api-gateway"))
    from routers.admin_domains.evals import summarize

    def row(ts: str, **cases: tuple[str, str]) -> dict:
        return {"value_json": json.dumps({"suite": "quant", "ts": ts, "model": "m", "cases": {c: {"status": s, "hash": h, "passes": 0, "n": 3, "type": "t", "failures": []} for c, (s, h) in cases.items()}})}

    q = summarize([row("2026-11-15T22:30:00Z", a=("always_fail", "h2"), b=("always_fail", "same")),
                   row("2026-11-14T22:30:00Z", a=("always_pass", "h1"), b=("always_pass", "same"))])[0]
    assert q["regressed"] == ["a", "b"] and q["edited"] == ["a"]   # only the case whose definition changed is marked


def test_evals_tab_run_now_only_runs_configured_suites_one_at_a_time(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    import asyncio
    import json
    import sys

    sys.path.insert(0, str(ROOT / "services/api-gateway"))
    from fastapi import HTTPException
    from routers.admin_domains import evals

    monkeypatch.setenv("DUCKCLAW_EVAL_COMMANDS", json.dumps({"quant": {"argv": [sys.executable, "-c", "import time; time.sleep(5)"], "cwd": str(tmp_path)}}))
    with pytest.raises(HTTPException) as e:
        asyncio.run(evals.run_eval_suite("nope"))
    assert e.value.status_code == 404
    try:
        assert asyncio.run(evals.run_eval_suite("quant"))["accepted"] and evals.is_running("quant")
        with pytest.raises(HTTPException) as e:
            asyncio.run(evals.run_eval_suite("quant"))
        assert e.value.status_code == 409
    finally:
        evals._RUNNING["quant"].kill()


def test_evals_tab_groups_cases_by_requirement_and_shows_gaps() -> None:
    import json
    import sys

    sys.path.insert(0, str(ROOT / "services/api-gateway"))
    from routers.admin_domains.evals import summarize

    run = {"suite": "q", "ts": "2026-11-06T22:30:00Z", "model": "m",
           "requirements": [{"id": "r1", "text": "T1", "question": "Q1"}, {"id": "r2", "text": "T2", "question": "Q2"}],
           "cases": {"a": {"status": "always_pass", "passes": 3, "n": 3, "type": "t", "failures": [], "requirement": "r1"},
                     "b": {"status": "flaky", "passes": 2, "n": 3, "type": "t", "failures": [], "requirement": "r1"},
                     "c": {"status": "always_pass", "passes": 3, "n": 3, "type": "t", "failures": [], "requirement": "undeclared"}}}
    got = {r["id"]: r for r in summarize([{"value_json": json.dumps(run)}])[0]["requirements"]}
    assert got["r1"]["cases"] == ["a", "b"] and got["r1"]["failing"] == ["b"] and got["r1"]["question"] == "Q1"
    assert got["r2"]["cases"] == [] and got["undeclared"]["cases"] == ["c"]


def test_evals_tab_priorities_and_saved_reviews(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio
    import json
    import sys

    sys.path.insert(0, str(ROOT / "services/api-gateway"))
    from routers.admin_domains import evals

    run = {"suite": "q", "ts": "2026-11-06T22:30:00Z", "cases": {
        "a": {"status": "always_fail", "severity": "high", "passes": 0, "n": 3, "type": "t", "failures": []},
        "b": {"status": "flaky", "severity": "low", "passes": 1, "n": 3, "type": "t", "failures": []},
        "c": {"status": "always_pass", "severity": "high", "passes": 3, "n": 3, "type": "t", "failures": []}}}
    suites = evals.summarize([{"value_json": json.dumps(run)}])
    got = suites[0]["latest"]["cases"]
    assert (got["a"]["priority"], got["b"]["priority"], got["c"]["priority"]) == ("fix_now", "improve_later", "")
    evals.attach_reviews(suites, [{"domain": "eval_notes", "key": "q:a", "value_json": json.dumps({"verdict": "fail", "note": "n"})}, {"domain": "eval_notes", "key": "q:zzz", "value_json": "{}"}])
    assert got["a"]["review"]["verdict"] == "fail" and "review" not in got["b"]

    sent = {}
    import duckclaw.db_write_queue as q
    monkeypatch.setattr(q, "enqueue_typed_command", lambda cmd, **kw: sent.update(cmd=cmd) or "t1")
    out = asyncio.run(evals.put_case_review("q", "a", evals.ReviewBody(note="n", possibility="p", verdict="unsure"), actor="juan"))
    assert out["task_id"] == "t1" and sent["cmd"].domain == "eval_notes" and sent["cmd"].key == "q:a" and sent["cmd"].value_json["verdict"] == "unsure"
    with pytest.raises(Exception):
        evals.ReviewBody(verdict="maybe")


def test_evals_tab_splits_the_score_by_difficulty_and_flags_stale_reviews() -> None:
    import json
    import sys

    sys.path.insert(0, str(ROOT / "services/api-gateway"))
    from routers.admin_domains.evals import summarize

    def case(status: str, diff: str, reviewed: str | None) -> dict:
        return {"status": status, "passes": 3, "n": 3, "type": "t", "failures": [], "difficulty": diff, **({"reviewed": reviewed} if reviewed else {})}

    run = {"suite": "q", "ts": "2026-11-05T22:30:00Z", "cases": {"a": case("always_pass", "easy", "2026-11-01"), "b": case("always_pass", "easy", "2026-01-01"),
                                                                  "c": case("always_fail", "hard", None), "d": case("always_pass", "hard", "2026-10-01")}}
    got = summarize([{"value_json": json.dumps(run)}])[0]
    assert got["by_difficulty"] == {"easy": [2, 2], "hard": [1, 2]} and got["review_due"] == ["b", "c"]

