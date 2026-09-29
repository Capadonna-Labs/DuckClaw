"""Regression: PUT /playground/model and /playground/slm must write under the
actor's real tenant, not a hardcoded "default" — a real user's own LLM pick
was landing in a shared "default" bucket that GET /playground/config only
found by accident (its own fallback-to-default chain), and any other caller
writing to that same shared bucket could silently clobber it."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from routers.admin_domains.playground.config_routes import _resolve_actor_tenant


def _fake_open_gateway_db(profile: dict):
    class _FakeDb:
        pass

    @contextmanager
    def _cm(*, read_only=True):
        yield _FakeDb()

    return _cm, profile


async def _run(actor: str, profile: dict | None, *, raise_on_lookup: bool = False):
    cm, _ = _fake_open_gateway_db(profile or {})

    def _fake_ensure_profile(_db, *, email):
        if raise_on_lookup:
            raise RuntimeError("hub unreachable")
        return profile or {}

    with patch("core.admin_identity.open_gateway_db", cm), patch(
        "duckclaw.admin_user_profiles.ensure_profile_for_user", side_effect=_fake_ensure_profile
    ):
        return await _resolve_actor_tenant(actor)


def test_resolves_the_actors_real_tenant() -> None:
    import asyncio

    result = asyncio.run(
        _run("juanjoarevalo57@gmail.com", {"tenant_id": "user-juanjoarevalo57-79c5ca60b91d4f3e"})
    )
    assert result == "user-juanjoarevalo57-79c5ca60b91d4f3e"


def test_falls_back_to_default_when_profile_has_no_tenant() -> None:
    import asyncio

    result = asyncio.run(_run("someone@example.com", {"tenant_id": ""}))
    assert result == "default"


def test_falls_back_to_default_on_lookup_failure_without_raising() -> None:
    import asyncio

    result = asyncio.run(_run("someone@example.com", None, raise_on_lookup=True))
    assert result == "default"
