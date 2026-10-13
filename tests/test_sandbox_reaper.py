"""Sandbox zombie reaper: idle/exited strix_sandbox_* containers are removed, active ones kept."""

from __future__ import annotations

import os
import time

import duckclaw.graphs.sandbox as sb


class _C:
    def __init__(self, sid: str, status: str = "running", created: str = "2026-10-01T00:00:00.123456789Z"):
        self.name = f"strix_sandbox_{sid}"
        self.status = status
        self.attrs = {"Created": created}


def test_reaper_removes_idle_and_exited_keeps_recent(monkeypatch, tmp_path) -> None:
    now = time.time()
    monkeypatch.setattr(sb, "_TMP_BASE", tmp_path)
    monkeypatch.delenv("DUCKCLAW_SANDBOX_IDLE_TTL_SEC", raising=False)
    monkeypatch.setenv("DUCKCLAW_SANDBOX_MAX_TIMEOUT_SEC", "3600")

    sb._touch_session("recent")  # used just now
    sb._touch_session("old")
    old_mark = tmp_path / "old" / sb._LAST_USED_MARK
    os.utime(old_mark, (now - 3 * 3600, now - 3 * 3600))  # idle 3 h > 2 h TTL
    sb._touch_session("exited")  # recent mark, but the container is dead

    containers = [_C("recent"), _C("old"), _C("exited", status="exited"), _C("nomark"), _C("current")]

    class _Client:
        class containers:  # noqa: N801
            @staticmethod
            def list(all: bool, filters: dict) -> list[_C]:  # noqa: A002
                return containers

    cleaned: list[str] = []

    class _Mgr:
        def cleanup(self, sid: str) -> None:
            cleaned.append(sid)

    monkeypatch.setattr(sb, "_docker_client", lambda: _Client())
    monkeypatch.setattr(sb, "_get_manager", lambda: _Mgr())

    reaped = sb.reap_idle_sandboxes(keep="current", now=now, force=True)

    # 'nomark' has no session mark: its container was created 2026-10-01 → idle.
    assert sorted(reaped) == ["exited", "nomark", "old"] == sorted(cleaned)
    # Throttle: a second unforced call within the window does nothing.
    assert sb.reap_idle_sandboxes(now=now + 1) == []


def test_idle_ttl_never_below_run_ceiling(monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_SANDBOX_IDLE_TTL_SEC", "60")
    monkeypatch.setenv("DUCKCLAW_SANDBOX_MAX_TIMEOUT_SEC", "3600")
    assert sb._sandbox_idle_ttl_sec() == 3900
