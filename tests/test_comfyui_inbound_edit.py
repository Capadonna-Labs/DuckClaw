"""Inbound ComfyUI edit routing (sin MLX-Vision)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_GW = _REPO / "services" / "api-gateway"
if str(_GW) not in sys.path:
    sys.path.insert(0, str(_GW))

from core.comfyui_inbound import (  # noqa: E402
    build_comfyui_edit_manager_text,
    comfyui_inbound_edit_enabled,
    should_route_comfyui_edit,
)


def test_comfyui_inbound_edit_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_COMFYUI_INBOUND_EDIT", raising=False)
    assert comfyui_inbound_edit_enabled() is False
    assert should_route_comfyui_edit(has_visual=True, caption="editar fondo") is False


def test_should_route_comfyui_edit_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_COMFYUI_INBOUND_EDIT", "1")
    assert should_route_comfyui_edit(has_visual=True, caption="cambiar fondo") is True
    assert should_route_comfyui_edit(has_visual=True, caption="", media_group_id="") is False
    assert should_route_comfyui_edit(has_visual=False, caption="x") is False
    assert should_route_comfyui_edit(
        has_visual=True, caption="x", media_group_id="album1"
    ) is False


def test_build_comfyui_edit_manager_text() -> None:
    path = "/tmp/db/private/u1/inbound/abc.jpg"
    out = build_comfyui_edit_manager_text(path, "quitar lentes")
    assert "COMFYUI_EDIT" in out
    assert path in out
    assert "edit_visual_asset" in out
    assert "quitar lentes" in out
