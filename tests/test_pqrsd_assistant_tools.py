"""Asistente PQRSD: manifiesto, skill HTTP acotado y tabla de desvío."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from duckclaw import DuckClaw
from duckclaw.workers.factory import (
    _build_worker_tools,
    _pqrsd_contact_only_skip_forced_fetch,
    _pqrsd_datos_first_over_forced_fetch,
    _pqrsd_rad_perfil_datos_first,
    _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch,
    _pqrsd_substantive_forced_fetch,
)
from duckclaw.workers.manifest import load_manifest

_REPO = Path(__file__).resolve().parents[1]
_SKILL_PATH = (
    _REPO
    / "packages/agents/src/duckclaw/forge/templates/PQRSD-Assistant/skills/pqrsd_portal_fetch.py"
)


def _load_pqrsd_skill():
    spec = importlib.util.spec_from_file_location("pqrsd_portal_fetch", _SKILL_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_pqrsd_substantive_forced_fetch_skips_greetings_and_thanks() -> None:
    assert _pqrsd_substantive_forced_fetch("hola", summarize_directive=False) is False
    assert _pqrsd_substantive_forced_fetch("gracias", summarize_directive=False) is False
    assert _pqrsd_substantive_forced_fetch(
        "A que correo pongo una queja por ruido?", summarize_directive=False
    ) is True
    assert _pqrsd_substantive_forced_fetch("x", summarize_directive=True) is False


def test_pqrsd_sandbox_prefers_chat_datos_over_forced_fetch() -> None:
    assert _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch("Quiero radicar una queja") is True
    assert _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch("Ayúdame a llenar el formulario PQRSD") is True
    assert _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch("PQRSD con identificación") is True
    assert _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch(
        "Sí, autorizo. Quiero poner una denuncia por violencia"
    ) is True
    assert _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch("autorizo que uses mis datos") is True
    assert _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch("no autorizo el uso de mis datos") is False
    assert _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch(
        "solo quiero saber cuánto demora un PQRSD"
    ) is False
    assert _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch(
        "solo quiero saber cuánto demora; también voy a radicar hoy"
    ) is True


def test_pqrsd_rad_perfil_datos_first() -> None:
    assert _pqrsd_rad_perfil_datos_first("Quiero hacer una solicitud") is True
    assert _pqrsd_rad_perfil_datos_first("Quiero hacer una petición de pqrsd") is True
    assert _pqrsd_rad_perfil_datos_first("petición de pqrsd") is True
    assert _pqrsd_rad_perfil_datos_first("Me gustaría hacer una denuncia pero no sé como") is True
    assert _pqrsd_rad_perfil_datos_first("Cómo puedo interponer una denuncia") is True
    assert _pqrsd_rad_perfil_datos_first("presentar una petición ante la alcaldía") is True
    assert _pqrsd_rad_perfil_datos_first("quiero presentar pqr ante la alcaldia") is True
    assert _pqrsd_rad_perfil_datos_first("solo quiero saber cuánto demora un PQRSD") is False
    assert _pqrsd_rad_perfil_datos_first("no autorizo guardar nada") is False


def test_pqrsd_datos_first_combines_sandbox_and_rad_perfil() -> None:
    assert _pqrsd_datos_first_over_forced_fetch("Quiero hacer una solicitud") is True
    assert _pqrsd_datos_first_over_forced_fetch("Quiero radicar una queja") is True


def test_pqrsd_contact_only_skip_forced_fetch() -> None:
    only_pii = (
        "Andrea Sofía Luján\n\n1.017.555.888\n\n"
        "Calle 50 # 40-10, Boston\n\nandrea.lujan.test@email.com"
    )
    assert _pqrsd_contact_only_skip_forced_fetch(only_pii) is True
    assert _pqrsd_contact_only_skip_forced_fetch("hola") is False
    with_story = only_pii + "\n\nAyer en Catastro el vigilante no me dejó entrar."
    assert _pqrsd_contact_only_skip_forced_fetch(with_story) is False


def test_pqrsd_manifest_loads() -> None:
    spec = load_manifest("PQRSD-Assistant")
    assert spec.logical_worker_id == "pqrsd_assistant"
    assert spec.read_only is False
    assert spec.network_access is True
    assert getattr(spec, "browser_sandbox", False) is True
    assert "pqrsd_portal_fetch" in (spec.skills_list or [])
    assert "pqrsd_radicacion_perfil" in (spec.skills_list or [])
    assert "pqrsd_radicacion_crm" in (spec.skills_list or [])
    assert "radicacion_crm" in (spec.allowed_tables or [])
    assert "pqrsd_sandbox_identificacion" in (spec.skills_list or [])
    assert getattr(spec, "research_config", None) is not None
    assert (spec.research_config or {}).get("tavily_enabled") is True
    pol = (
        _REPO
        / "packages/agents/src/duckclaw/forge/templates/PQRSD-Assistant/security_policy.yaml"
    )
    assert pol.is_file()


def test_strip_mercenary_spec_for_pqrsd_assistant() -> None:
    from duckclaw.graphs.manager_graph import _strip_mercenary_spec_for_pqrsd_assistant

    out = {"assigned_worker_id": "PQRSD-Assistant", "mercenary_spec": {"directive": "x", "timeout": 30}}
    assert _strip_mercenary_spec_for_pqrsd_assistant(out) is True
    assert "mercenary_spec" not in out
    out2 = {"assigned_worker_id": "finanz", "mercenary_spec": {"directive": "x", "timeout": 30}}
    assert _strip_mercenary_spec_for_pqrsd_assistant(out2) is True
    assert "mercenary_spec" not in out2
    out3 = {"assigned_worker_id": "Manager", "mercenary_spec": {"directive": "x", "timeout": 30}}
    assert _strip_mercenary_spec_for_pqrsd_assistant(out3) is False
    assert "mercenary_spec" in out3


def test_pqrsd_tools_registered(tmp_path: Path) -> None:
    db = DuckClaw(str(tmp_path / "pqrsd.duckdb"))
    spec = load_manifest("PQRSD-Assistant")
    tools = _build_worker_tools(db, spec)
    names = {t.name for t in tools}
    assert "pqrsd_fetch_canonical" in names
    assert "pqrsd_entity_routing" in names
    assert "pqrsd_upsert_radicacion_perfil" in names
    assert "pqrsd_registrar_radicacion_crm" in names
    assert "admin_sql" in names
    assert "pqrsd_run_identificacion_step1" in names


def test_pqrsd_fetch_unknown_page() -> None:
    mod = _load_pqrsd_skill()
    out = json.loads(mod.pqrsd_fetch_canonical_impl("no_existe"))
    assert out.get("error") == "page_key_desconocido"
    assert "pqrsd_home" in (out.get("permitidos") or [])


def test_pqrsd_fetch_redirect_blocked() -> None:
    mod = _load_pqrsd_skill()
    resp = MagicMock()
    resp.status_code = 200
    resp.url = "https://evil.example/phish"
    resp.text = "<html><body>no</body></html>"
    resp.raise_for_status = MagicMock()
    with patch.object(mod.requests, "get", return_value=resp):
        out = json.loads(mod.pqrsd_fetch_canonical_impl("pqrsd_home"))
    assert out.get("error") == "redirect_a_host_no_permitido"


def test_pqrsd_fetch_ok_truncates() -> None:
    mod = _load_pqrsd_skill()
    long_body = "<html><body>" + ("x" * 120_000) + "</body></html>"
    resp = MagicMock()
    resp.status_code = 200
    resp.url = "https://www.medellin.gov.co/es/pqrsd/"
    resp.text = long_body
    resp.raise_for_status = MagicMock()
    with patch.object(mod.requests, "get", return_value=resp):
        out = json.loads(mod.pqrsd_fetch_canonical_impl("pqrsd_home"))
    assert out.get("status") == 200
    assert "truncado" in (out.get("text") or "") or len(out.get("text", "")) <= mod._MAX_TEXT_CHARS + 30


def test_pqrsd_entity_routing_returns_rows() -> None:
    mod = _load_pqrsd_skill()
    out = json.loads(mod.pqrsd_entity_routing_impl())
    rows = out.get("rows")
    assert isinstance(rows, list)
    assert any("Emvarias" in str(r.get("entity", "")) for r in rows)
