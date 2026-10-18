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
    from duckclaw.directive_skills import DIRECTIVE_SCOPE_NOTE

    assert msg == f"[DIRECTIVA ACTIVA: /ponytail]\nSé breve y directo.\n\n{DIRECTIVE_SCOPE_NOTE}\n\narregla este bug"
    assert rest == "arregla este bug"


def test_matching_skill_with_no_trailing_text() -> None:
    with patch(
        "core.admin_identity.open_gateway_db",
        _fake_open_gateway_db([("Sé breve.",)]),
    ):
        msg, rest = extract_directive_skill("/ponytail", tenant_id="t1", actor_email="a@b.com")
    from duckclaw.directive_skills import DIRECTIVE_SCOPE_NOTE

    assert msg == f"[DIRECTIVA ACTIVA: /ponytail]\nSé breve.\n\n{DIRECTIVE_SCOPE_NOTE}"
    assert rest == ""


def test_db_error_fails_open_without_raising() -> None:
    with patch("core.admin_identity.open_gateway_db", side_effect=RuntimeError("down")):
        msg, rest = extract_directive_skill("/ponytail x", tenant_id="t1", actor_email="a@b.com")
    assert msg == "/ponytail x"
    assert rest is None


def test_framework_directive_skills_seed_once_and_apply_to_any_tenant() -> None:
    import duckdb

    from duckclaw.directive_skills import expand_directive_skill, seed_framework_directive_skills

    con = duckdb.connect()
    con.execute(
        "CREATE TABLE main.admin_skills (skill_id VARCHAR, name VARCHAR, description VARCHAR, skill_type VARCHAR, "
        "implementation_ref VARCHAR, owner_email VARCHAR, tenant_id VARCHAR, visibility VARCHAR, active BOOLEAN)"
    )
    assert seed_framework_directive_skills(con) == 2
    assert seed_framework_directive_skills(con) == 0  # idempotent, never overwrites
    assert con.execute("SELECT max(length(description)) FROM main.admin_skills").fetchone()[0] <= 4096

    msg, rest = expand_directive_skill(con, "/debug el login falla", tenant_id="t1", actor_email="a@b.com")
    assert msg.startswith("[DIRECTIVA ACTIVA: /debug]") and "Bucle de feedback" in msg and rest == "el login falla"

    # A tenant's own skill with the same name wins over the framework default.
    con.execute("UPDATE main.admin_skills SET name = 'debug_fw' WHERE name = 'debug'")
    con.execute("INSERT INTO main.admin_skills VALUES ('s1','debug','MIO','directive','directive://debug','a@b.com','t1','private',true)")
    con.execute("UPDATE main.admin_skills SET name = 'debug' WHERE name = 'debug_fw'")
    msg, _ = expand_directive_skill(con, "/debug x", tenant_id="t1", actor_email="a@b.com")
    assert msg.startswith("[DIRECTIVA ACTIVA: /debug]\nMIO")


def test_spoken_skill_maps_to_slash() -> None:
    from duckclaw.directive_skills import spoken_skill_to_slash

    names = ["revisar_correos", "apertura", "team_digest", "weekly_digest", "onboarding", "backtest"]
    assert spoken_skill_to_slash(names, "Usa la skill revisar correo.") == "/revisar_correos"
    assert spoken_skill_to_slash(names, "corre el comando apertura de hoy") == "/apertura de hoy"
    assert spoken_skill_to_slash(names, "ejecuta la skill team digest") == "/team_digest"
    assert spoken_skill_to_slash(names, "Usa el revisar correo.") is None  # no trigger word
    assert spoken_skill_to_slash(names, "comando inexistente xyz") is None
    # STT heard "setups" (said in Spanish) as "PS": an alias maps it.
    assert spoken_skill_to_slash(names, "Ejecuta el comando PS", {"ps": "setups"}) is None  # not in names
    assert spoken_skill_to_slash(names + ["setups"], "Ejecuta el comando PS", {"ps": "setups"}) == "/setups"
    assert spoken_skill_to_slash(names + ["setups"], "comando P S de hoy", {"ps": "setups"}) == "/setups de hoy"


def test_dedupe_by_name_keeps_first_row_case_insensitive() -> None:
    from duckclaw.directive_skills import dedupe_by_name

    rows = [{"name": "debug", "description": "MIO"}, {"name": "Debug", "description": "framework"}, ("other", 1)]
    assert dedupe_by_name(rows) == [{"name": "debug", "description": "MIO"}, ("other", 1)]
