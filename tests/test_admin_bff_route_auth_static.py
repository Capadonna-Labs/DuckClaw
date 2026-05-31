"""Static guards for admin BFF route authentication.

The auth spec requires RBAC and actor identity to be derived from the server
session, never from spoofable browser headers.
"""

from __future__ import annotations

from pathlib import Path


ADMIN_ROUTE_DIR = (
    Path(__file__).resolve().parents[1] / "apps" / "duckclaw-admin" / "src" / "app" / "api" / "admin"
)


def test_admin_bff_routes_do_not_trust_client_role_or_actor_headers() -> None:
    offenders: list[str] = []
    for path in sorted(ADMIN_ROUTE_DIR.rglob("route.ts")):
        text = path.read_text(encoding="utf-8")
        if "x-duckclaw-role" in text or "x-duckclaw-actor" in text:
            offenders.append(str(path.relative_to(ADMIN_ROUTE_DIR)))

    assert offenders == []
