"""Tests Fal bridge (mock async pipeline)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from duckclaw.forge.skills import fal_bridge


class _FakeDb:
    _read_only = False

    def execute(self, sql: str) -> None:
        pass

    def query(self, sql: str):
        return json.dumps([{"total": 0.0}])


@pytest.fixture(autouse=True)
def _env_fal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAL_KEY", "test-fal-key")
    monkeypatch.setenv("DUCKCLAW_MEDIA_DAILY_BUDGET_USD", "5.0")


def test_register_fal_skill_adds_three_tools() -> None:
    tools: list[Any] = []
    fal_bridge.register_fal_skill(tools, {"enabled": True})
    names = {t.name for t in tools}
    assert names == {"generate_flux_image", "generate_kling_video", "execute_comfy_workflow"}


def test_fal_queue_urls_from_submit_uses_api_urls() -> None:
    status, response = fal_bridge._fal_queue_urls_from_submit(
        {
            "status_url": "https://queue.fal.run/fal-ai/flux/requests/abc/status",
            "response_url": "https://queue.fal.run/fal-ai/flux/requests/abc",
        },
        "fal-ai/flux/dev",
        "abc",
    )
    assert status.endswith("/abc/status")
    assert response.endswith("/abc")


def test_fal_queue_urls_fallback_strips_dev_subpath() -> None:
    status, response = fal_bridge._fal_queue_urls_from_submit(
        {},
        "fal-ai/flux/dev",
        "rid-1",
    )
    assert "/fal-ai/flux/requests/rid-1/status" in status
    assert "/fal-ai/flux/requests/rid-1" == response


def test_extract_media_url_image() -> None:
    url = fal_bridge._extract_media_url(
        {"response": {"images": [{"url": "https://cdn.example/x.png"}]}},
        "image",
    )
    assert url == "https://cdn.example/x.png"


async def _fake_fal_generate(**kwargs: Any) -> str:
    return json.dumps({
        "ok": True,
        "success": True,
        "media_url": "https://cdn.example/x.png",
        "file_path": "/tmp/x.png",
        "latency_sec": 1.0,
        "cost_usd": 0.025,
    })


def test_generate_flux_image_impl_delegates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fal_bridge, "_fal_generate_async", _fake_fal_generate)
    out = json.loads(
        fal_bridge._generate_flux_image_impl("studio orb", duckclaw_db=_FakeDb())
    )
    assert out.get("ok") is True
    assert out.get("success") is True
