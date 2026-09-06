"""Admin crons domain: filters PM2 jlist to cron-scheduled processes, generically.

No hardcoded job names/paths — anything with a non-empty pm2_env.cron_restart shows up.
"""

from __future__ import annotations

import json

import pytest

from gateway_import import ensure_gateway_on_sys_path

ensure_gateway_on_sys_path()


def _jlist(*procs: dict) -> str:
    return json.dumps(list(procs))


def _proc(name: str, cron: str | None, **env_overrides) -> dict:
    env = {
        "status": "online",
        "restart_time": 0,
        "unstable_restarts": 0,
        "pm_cwd": "/some/path",
        "exec_interpreter": "node",
        "pm_exec_path": "/some/path/index.js",
        "created_at": 0,
        "pm_uptime": 0,
    }
    if cron is not None:
        env["cron_restart"] = cron
    env.update(env_overrides)
    return {"name": name, "pm_id": 0, "pm2_env": env}


def test_filters_to_processes_with_cron_restart_only() -> None:
    from routers.admin_domains.crons import _cron_processes_from_jlist

    raw = _jlist(
        _proc("DuckClaw-Gateway", None),
        _proc("some-vertical-job", "*/15 8-15 * * 1-5"),
        _proc("another-job", "0 7 * * 1-5"),
    )

    out = _cron_processes_from_jlist(raw)
    names = {p["name"] for p in out}

    assert names == {"some-vertical-job", "another-job"}
    assert "DuckClaw-Gateway" not in names


def test_empty_cron_restart_string_excluded() -> None:
    from routers.admin_domains.crons import _cron_processes_from_jlist

    raw = _jlist(_proc("job-with-blank-cron", ""))

    assert _cron_processes_from_jlist(raw) == []


def test_malformed_jlist_raises_problem() -> None:
    from routers.admin_domains.crons import _cron_processes_from_jlist

    with pytest.raises(Exception):
        _cron_processes_from_jlist("not json")


def test_strip_ansi_removes_pm2_color_codes() -> None:
    from routers.admin_domains.crons import _strip_ansi

    raw = "\x1b[1m\x1b[90m[TAILING] Tailing last 200 lines\x1b[39m\x1b[22m\nplain line"

    assert _strip_ansi(raw) == "[TAILING] Tailing last 200 lines\nplain line"


def test_guard_rejects_name_not_currently_cron_scheduled(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from routers.admin_domains import crons

    async def _fake_list() -> list[dict]:
        return [{"name": "known-cron"}]

    monkeypatch.setattr(crons, "_list_cron_processes", _fake_list)

    with pytest.raises(Exception):
        asyncio.run(crons._guard_known_cron("DuckClaw-Gateway"))

    # Known cron passes without raising.
    asyncio.run(crons._guard_known_cron("known-cron"))
