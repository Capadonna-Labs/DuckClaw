"""Tests for Android MCP screenshot → artifact vision pipeline."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

_TINY_PNG = base64.standard_b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xdb"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
).decode("ascii")


def test_parse_mcp_screenshot_bytes_from_repr() -> None:
    from duckclaw.mcp_android_vision import parse_mcp_screenshot_bytes

    raw = f"type='image' data='{_TINY_PNG}'"
    out = parse_mcp_screenshot_bytes(raw)
    assert out is not None
    assert len(out) > 8


def test_process_android_screenshot_tool_result_persists_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from duckclaw import mcp_android_vision as vision

    monkeypatch.setattr(
        vision,
        "_tenant_artifacts_dir",
        lambda _tid: tmp_path,
    )
    raw = f"type='image' data='{_TINY_PNG}'"
    content, sidecar = vision.process_android_screenshot_tool_result(raw, tenant_id="default")
    payload = json.loads(content)
    assert payload.get("ok") is True
    assert payload.get("vision") is True
    assert payload.get("artifact_id")
    assert sidecar.get("figure_base64")
    assert (tmp_path / f"{payload['artifact_id']}.png").is_file()


def test_is_android_screenshot_tool() -> None:
    from duckclaw.mcp_android_vision import is_android_screenshot_tool

    assert is_android_screenshot_tool("mcp__android__get_screenshot")
    assert not is_android_screenshot_tool("mcp__android__swipe_screen")
