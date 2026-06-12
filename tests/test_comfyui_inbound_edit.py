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
    ingest_admin_visual_edit_inbound,
    should_route_admin_playground_edit,
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


def test_should_route_admin_playground_edit() -> None:
    assert should_route_admin_playground_edit(caption="cambiar fondo", image_count=1) is True
    assert should_route_admin_playground_edit(caption="", image_count=1) is False
    assert should_route_admin_playground_edit(caption="x", image_count=2) is False


def test_ingest_admin_visual_edit_inbound(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw import vaults

    monkeypatch.setattr(vaults, "db_root", lambda: tmp_path / "db")
    out = ingest_admin_visual_edit_inbound(
        image_bytes=b"\xff\xd8" + b"\x00" * 20,
        caption="ropa amarilla",
        tenant_id="tenant_admin",
        mime_type="image/jpeg",
    )
    assert "COMFYUI_EDIT" in out
    assert "edit_visual_asset" in out
    assert "ropa amarilla" in out


def test_build_comfyui_edit_manager_text() -> None:
    path = "/tmp/db/private/u1/inbound/abc.jpg"
    out = build_comfyui_edit_manager_text(path, "quitar lentes")
    assert "COMFYUI_EDIT" in out
    assert path in out
    assert "edit_visual_asset" in out
    assert "quitar lentes" in out


def test_parse_comfyui_edit_inbound_from_manager_text() -> None:
    from duckclaw.workers.factory import _parse_comfyui_edit_inbound

    path = "/root/db/private/t1/inbound/abc.jpg"
    out = build_comfyui_edit_manager_text(path, "Pon fondo de playa")
    parsed = _parse_comfyui_edit_inbound(out)
    assert parsed is not None
    assert parsed["source_image_path"] == path
    assert parsed["edit_prompt"] == "Pon fondo de playa"
