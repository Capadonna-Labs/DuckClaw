"""browser_image_available — sin pull Docker."""

from __future__ import annotations

import pytest


def test_browser_image_available_false_without_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import sandbox as sb

    monkeypatch.setattr(sb, "_docker_available", lambda: False)
    assert sb.browser_image_available() is False


def test_browser_image_available_true_when_image_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import sandbox as sb

    class FakeImages:
        def get(self, _name: str) -> object:
            return object()

    class FakeClient:
        images = FakeImages()

    monkeypatch.setattr(sb, "_docker_available", lambda: True)
    monkeypatch.setattr(sb, "_docker_client", lambda: FakeClient())
    assert sb.browser_image_available() is True


def test_run_browser_sandbox_fast_fail_missing_image(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import sandbox as sb

    monkeypatch.setattr(sb, "browser_image_available", lambda: False)
    tool = sb.browser_sandbox_tool_factory(db=None, llm=None)
    raw = tool.invoke({"url": "https://www.mql5.com/es/code/1"})
    import json

    payload = json.loads(raw)
    assert payload.get("exit_code") == 1
    assert payload.get("browser_image_missing") is True
