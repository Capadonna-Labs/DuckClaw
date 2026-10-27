"""Socrata open-data skill: allowlisted portals only, valid dataset ids, capped rows, read-only."""
from __future__ import annotations

import json
import os

import pytest

from duckclaw.forge.skills import socrata_bridge as m

ALLOWED = ["www.datos.gov.co"]


def test_query_builds_the_soda_url_with_a_row_cap() -> None:
    seen = {}

    def fetch(url):
        seen["url"] = url
        return [{"id_contrato": "CO1"}]

    out = json.loads(m.socrata_query_impl("JBJY-VK9H", where="departamento='Antioquia'", select="id_contrato", limit=9999, allowed=ALLOWED, fetch=fetch))
    assert seen["url"].startswith("https://www.datos.gov.co/resource/jbjy-vk9h.json?")
    assert "%24limit=200" in seen["url"] and "%24where=departamento%3D%27Antioquia%27" in seen["url"]
    assert out["filas"] == 1 and out["dataset"] == "jbjy-vk9h"


def test_only_allowlisted_portals_and_well_formed_ids() -> None:
    assert "no permitido" in m.socrata_query_impl("jbjy-vk9h", domain="evil.example", allowed=ALLOWED, fetch=lambda u: [])
    assert "no permitido" in m.socrata_search_impl("x", domain="169.254.169.254", allowed=ALLOWED, fetch=lambda u: {})
    assert "inválido" in m.socrata_query_impl("../../etc", allowed=ALLOWED, fetch=lambda u: [])


def test_big_results_are_clipped_and_errors_do_not_raise() -> None:
    out = m.socrata_query_impl("jbjy-vk9h", allowed=ALLOWED, fetch=lambda u: [{"x": "y" * 100}] * 500)
    assert len(out) < m.MAX_CHARS + 100 and "recortado" in out

    def boom(u):
        raise TimeoutError

    assert "TimeoutError" in m.socrata_query_impl("jbjy-vk9h", allowed=ALLOWED, fetch=boom)


def test_registers_two_tools_with_the_default_portal_and_custom_domains() -> None:
    tools: list = []
    m.register_socrata_skill(tools, {})
    assert [t.name for t in tools] == ["socrata_search", "socrata_query"] and "www.datos.gov.co" in tools[1].description
    assert m._domains({"domains": ["Data.CityOfNewYork.us"]}) == ["data.cityofnewyork.us"]


@pytest.mark.skipif(not os.environ.get("RUN_NETWORK_TESTS"), reason="red: RUN_NETWORK_TESTS=1")
def test_live_secop_query() -> None:
    out = json.loads(m.socrata_query_impl("jbjy-vk9h", select="nombre_entidad,valor_del_contrato", limit=3, allowed=ALLOWED))
    assert out["filas"] == 3
