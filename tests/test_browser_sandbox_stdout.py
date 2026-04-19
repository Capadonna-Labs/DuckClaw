"""run_browser_sandbox debe serializar stdout_tail/stderr_tail para el LLM."""

from __future__ import annotations

import json
from unittest.mock import patch

from duckclaw.graphs.sandbox import (
    ExecutionResult,
    _coerce_playwright_headed_for_novnc,
    _default_browser_script_for_open_url,
    browser_sandbox_tool_factory,
)


def test_default_browser_script_for_open_url_contains_goto() -> None:
    s = _default_browser_script_for_open_url("https://www.example.com/path?q=1")
    assert "https://www.example.com/path?q=1" in s
    assert "page.goto" in s or "goto(" in s
    assert "chrome_vnc_show" in s
    assert "_spawn_visible_chromium" in s


def test_browser_sandbox_accepts_url_without_code(monkeypatch: object) -> None:
    captured: dict[str, str] = {}

    def _capture(**kwargs: object) -> ExecutionResult:
        captured["code"] = str(kwargs.get("code", ""))
        return ExecutionResult(
            exit_code=0,
            stdout='{"url": "https://x.test/"}',
            stderr="",
            timed_out=False,
            artifacts=[],
            attempts=1,
        )

    tool = browser_sandbox_tool_factory(None, None)
    with patch("duckclaw.graphs.sandbox.run_in_sandbox", side_effect=_capture):
        raw = tool.invoke({"url": "https://www.medellin.gov.co/es/pqrsd/"})

    assert "medellin.gov.co" in captured["code"]
    data = json.loads(raw)
    assert data.get("exit_code") == 0
    assert "stdout_tail" in data


def test_browser_sandbox_tool_includes_stdout_and_stderr_tails() -> None:
    payload = '{"extracted": true, "source": "mql5"}\n'
    fake = ExecutionResult(
        exit_code=0,
        stdout=payload,
        stderr="selector article: timeout\n",
        timed_out=False,
        artifacts=[],
        attempts=1,
    )
    tool = browser_sandbox_tool_factory(None, None)
    with patch("duckclaw.graphs.sandbox.run_in_sandbox", return_value=fake):
        raw = tool.invoke({"code": "print('x')"})

    assert isinstance(raw, str)
    data = json.loads(raw)
    assert "stdout_tail" in data
    assert "extracted" in data["stdout_tail"]
    assert "stderr_tail" in data
    assert "selector article" in data["stderr_tail"]


def test_coerce_playwright_headed_replaces_true(monkeypatch: object) -> None:
    monkeypatch.delenv("DUCKCLAW_BROWSER_PLAYWRIGHT_HEADLESS", raising=False)
    src = "await p.chromium.launch_persistent_context(headless=True, user_data_dir='/x')"
    out = _coerce_playwright_headed_for_novnc(src)
    assert "headless=False" in out
    assert "headless=True" not in out


def test_coerce_playwright_headed_respects_opt_out(monkeypatch: object) -> None:
    monkeypatch.setenv("DUCKCLAW_BROWSER_PLAYWRIGHT_HEADLESS", "1")
    src = "launch(headless=True)"
    assert _coerce_playwright_headed_for_novnc(src) == src
