from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_auth_proxy_maps_gateway_fetch_failures_to_503() -> None:
    text = (ROOT / "apps/duckclaw-admin/src/lib/authProxy.ts").read_text(encoding="utf-8")

    assert "gateway_unreachable" in text
    assert "catch" in text
    assert "status: 503" in text


def test_admin_middleware_allows_next_dev_hydration() -> None:
    text = (ROOT / "apps/duckclaw-admin/src/middleware.ts").read_text(encoding="utf-8")

    assert "isDev" in text
    assert "'unsafe-eval'" in text
    assert "'unsafe-inline'" in text
