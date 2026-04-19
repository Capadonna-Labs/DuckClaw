"""Tests: generador Playwright PQRSD y validación de entrada."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from duckclaw.forge.atoms.pqrsd_radicacion_playwright import (
    build_pqrsd_identificacion_playwright_script,
    emails_match,
    normalize_document_number,
)
from duckclaw.graphs.sandbox import _sandbox_stdout_suggests_success_despite_exit

_SKILL_PATH = (
    Path(__file__).resolve().parent.parent
    / "packages/agents/src/duckclaw/forge/templates/PQRSD-Assistant/skills/pqrsd_sandbox_identificacion.py"
)
_spec = importlib.util.spec_from_file_location("pqrsd_sandbox_identificacion_under_test", _SKILL_PATH)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
PqrsdIdentificacionInput = _mod.PqrsdIdentificacionInput
TOOL_NAME = _mod.TOOL_NAME


def test_normalize_document_number_strips_spaces() -> None:
    assert normalize_document_number("  12 345  ") == "12345"


def test_emails_match_case_insensitive() -> None:
    assert emails_match("A@B.CO", "a@b.co")
    assert not emails_match("a@b.co", "x@y.co")


def test_build_script_embeds_tipo_as_json_string() -> None:
    s = build_pqrsd_identificacion_playwright_script(
        modo="identificada",
        tipo_documento='Cédula"; import os; os.system("evil")',
        numero_documento="123",
        correo="u@example.com",
        correo_confirmacion="u@example.com",
    )
    assert "TIPO_DOC = " in s
    assert 'os.system("evil")' not in s


def test_build_script_includes_modo_and_playwright() -> None:
    s = build_pqrsd_identificacion_playwright_script(
        modo="anonima",
        tipo_documento=None,
        numero_documento=None,
        correo="x@y.com",
        correo_confirmacion="x@y.com",
    )
    assert "MODO = " in s
    assert '"anonima"' in s
    assert "async_playwright" in s
    assert "pqrsd_identificacion_step1.png" in s
    assert "_accept_privacy_consent" in s
    assert "get_by_role('switch'" in s
    assert "await _accept_privacy_consent(page)" in s
    assert "_first_visible_form_select" in s
    assert "goog-te-combo" in s
    assert "select_secretarias" in s
    assert "_select_looks_like_tipo_documento" in s
    assert "_select_option_texts" in s
    assert "_mercurio_frame" in s
    assert "iframe-pqrs" in s
    assert "tipoDocumento" in s
    assert "mercurio_iframe" in s
    assert "_iframe_has_identificacion_step1" in s
    assert "iframe_form_ready" in s
    assert "radicacion_path" in s


def test_pqrsd_identificacion_input_requires_consent() -> None:
    with pytest.raises(ValidationError):
        PqrsdIdentificacionInput(
            modo="identificada",
            consentimiento_usuario=False,
            tipo_documento="Cédula de ciudadanía",
            numero_documento="1",
            correo="a@b.co",
            correo_confirmacion="a@b.co",
        )


def test_pqrsd_identificacion_input_identificada_requires_docs() -> None:
    with pytest.raises(ValidationError):
        PqrsdIdentificacionInput(
            modo="identificada",
            consentimiento_usuario=True,
            tipo_documento=None,
            numero_documento=None,
            correo="a@b.co",
            correo_confirmacion="a@b.co",
        )


def test_tool_name_constant() -> None:
    assert TOOL_NAME == "pqrsd_run_identificacion_step1"


def test_sandbox_stdout_heuristic_sigterm_after_json() -> None:
    stdout = (
        '{"ok": true, "step": "identificacion_solicitar_verificacion", '
        '"url": "https://www.medellin.gov.co/es/pqrsd/foo", "title": "PQRSD", "modo": "identificada"}\n'
    )
    assert _sandbox_stdout_suggests_success_despite_exit(stdout, exit_code=143)
    assert not _sandbox_stdout_suggests_success_despite_exit(stdout, exit_code=124)
