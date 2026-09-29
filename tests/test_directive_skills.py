"""Tests for the "/nombre" directive-skill injection (playground chat turn prep)."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from routers.admin_domains.playground.directive_skills import extract_directive_skill


class _FakeDb:
    def __init__(self, rows: list) -> None:
        self._rows = rows

    def execute(self, _sql, _params=None):
        return self._rows


def _fake_open_gateway_db(rows: list):
    @contextmanager
    def _cm(*, read_only=True):
        yield _FakeDb(rows)

    return _cm


def test_non_slash_message_untouched() -> None:
    assert extract_directive_skill("hola mundo", tenant_id="t1", actor_email="a@b.com") == (
        "hola mundo",
        None,
    )


def test_slash_with_no_matching_skill_untouched() -> None:
    with patch(
        "core.admin_identity.open_gateway_db", _fake_open_gateway_db([])
    ):
        msg, rest = extract_directive_skill("/nope algo", tenant_id="t1", actor_email="a@b.com")
    assert msg == "/nope algo"
    assert rest is None


def test_matching_skill_injects_description_and_strips_prefix() -> None:
    with patch(
        "core.admin_identity.open_gateway_db",
        _fake_open_gateway_db([("Sé breve y directo.",)]),
    ):
        msg, rest = extract_directive_skill(
            "/ponytail arregla este bug", tenant_id="t1", actor_email="a@b.com"
        )
    assert msg == "[DIRECTIVA ACTIVA: /ponytail]\nSé breve y directo.\n\narregla este bug"
    assert rest == "arregla este bug"


def test_matching_skill_with_no_trailing_text() -> None:
    with patch(
        "core.admin_identity.open_gateway_db",
        _fake_open_gateway_db([("Sé breve.",)]),
    ):
        msg, rest = extract_directive_skill("/ponytail", tenant_id="t1", actor_email="a@b.com")
    assert msg == "[DIRECTIVA ACTIVA: /ponytail]\nSé breve."
    assert rest == ""


def test_db_error_fails_open_without_raising() -> None:
    with patch("core.admin_identity.open_gateway_db", side_effect=RuntimeError("down")):
        msg, rest = extract_directive_skill("/ponytail x", tenant_id="t1", actor_email="a@b.com")
    assert msg == "/ponytail x"
    assert rest is None
