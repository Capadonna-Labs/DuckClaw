"""
Paso 1 de radicación PQRSD en el sandbox browser (Playwright generado en atoms).

Spec: specs/features/Asistente PQRSD (Alcaldía Medellín).md
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field, field_validator, model_validator

from duckclaw.forge.atoms.pqrsd_radicacion_playwright import (
    build_pqrsd_identificacion_playwright_script,
    emails_match,
    normalize_document_number,
)
from duckclaw.graphs.sandbox import (
    _BROWSER_SANDBOX_STDERR_TAIL,
    _BROWSER_SANDBOX_STDOUT_TAIL,
    _browser_image_name,
    _browser_vnc_url_for_session,
    _sandbox_stdout_suggests_success_despite_exit,
    run_in_sandbox,
)

TOOL_NAME = "pqrsd_run_identificacion_step1"


def _debug_pqrsd_step1_log(result: Any, *, session_id: str) -> None:
    # #region agent log
    """NDJSON local para verificar hipótesis de flujo (sin PII)."""
    tail = (result.stdout or "")[-6000:]
    ok_hint: bool | None = None
    if '"ok": true' in tail:
        ok_hint = True
    elif '"ok": false' in tail:
        ok_hint = False
    root = Path(__file__).resolve()
    for _ in range(14):
        if (root / ".cursor").is_dir():
            break
        parent = root.parent
        if parent == root:
            return
        root = parent
    log_path = root / ".cursor" / "debug-8d6707.log"
    payload = {
        "sessionId": "8d6707",
        "timestamp": int(time.time() * 1000),
        "location": "pqrsd_sandbox_identificacion.py:_run",
        "message": "pqrsd_run_identificacion_step1 sandbox finished",
        "data": {
            "exit_code": int(result.exit_code or 0),
            "timed_out": bool(result.timed_out),
            "stdout_ok_hint": ok_hint,
            "has_error_key": '"error"' in tail,
            "session_id_nonempty": bool((session_id or "").strip()),
            "goog_te_in_stdout": "goog-te-combo" in tail,
            "select_secretarias_in_stdout": "select_secretarias" in tail,
            "mercurio_iframe_in_stdout": "mercurio_iframe" in tail,
            "radicacion_iframe_form_ready_in_stdout": "iframe_form_ready" in tail,
            "radicacion_clicked_parent_in_stdout": "clicked_parent" in tail,
        },
        "hypothesisId": "H_parent_vs_iframe_radicacion_button",
    }
    try:
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass
    # #endregion


class PqrsdIdentificacionInput(BaseModel):
    """Entrada validada; el LLM no inyecta código Playwright en bruto."""

    modo: str = Field(
        ...,
        description="identificada o anonima",
        pattern="^(identificada|anonima)$",
    )
    consentimiento_usuario: bool = Field(
        ...,
        description=(
            "Obligatorio en el JSON de la tool: true si el usuario ya dijo sí/autorizo/consiento "
            "para escribir en el formulario del navegador. Si falta o es false, la tool falla."
        ),
    )
    tipo_documento: str | None = Field(None, description="Ej. Cédula de ciudadanía (solo si modo=identificada).")
    numero_documento: str | None = Field(None, description="Número sin espacios extra (solo identificada).")
    correo: str | None = Field(None, description="Correo para verificación.")
    correo_confirmacion: str | None = Field(None, description="Debe coincidir con correo.")
    session_id: str = Field("", description="Sesión sandbox (el gateway suele inyectarlo desde el chat).")
    worker_id: str = Field("", description="Worker Forge (el gateway suele inyectarlo).")

    @field_validator("modo", mode="before")
    @classmethod
    def _strip_modo(cls, v: object) -> object:
        if isinstance(v, str):
            return v.strip()
        return v

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> PqrsdIdentificacionInput:
        if not self.consentimiento_usuario:
            raise ValueError("Se requiere consentimiento_usuario=True tras confirmación explícita en el chat.")
        ce = (self.correo or "").strip()
        c2 = (self.correo_confirmacion or "").strip()
        if not ce or not c2:
            raise ValueError("correo y correo_confirmacion son obligatorios.")
        if not emails_match(ce, c2):
            raise ValueError("correo y correo_confirmacion deben coincidir.")
        if str(self.modo) == "identificada":
            if not (self.tipo_documento or "").strip():
                raise ValueError("tipo_documento es obligatorio para modo identificada.")
            if not (self.numero_documento or "").strip():
                raise ValueError("numero_documento es obligatorio para modo identificada.")
        return self


def _format_tool_json(
    result: Any,
    *,
    session_id: str,
) -> str:
    effective_ok = result.exit_code == 0 and not result.timed_out
    if not effective_ok and _sandbox_stdout_suggests_success_despite_exit(
        result.stdout or "", exit_code=int(result.exit_code or 0)
    ):
        effective_ok = True
    st = "success" if effective_ok else "error"
    out: dict[str, Any] = {
        "exit_code": result.exit_code,
        "status": st,
        "stdout_tail": (result.stdout or "")[-_BROWSER_SANDBOX_STDOUT_TAIL:],
        "stderr_tail": (result.stderr or "")[-_BROWSER_SANDBOX_STDERR_TAIL:],
    }
    if result.exit_code != 0 and not result.timed_out and effective_ok:
        out["note"] = (
            "Salida JSON útil detectada pese a código de salida no cero "
            "(p. ej. SIGTERM tras completar el script)."
        )
    if result.artifacts:
        out["artifacts"] = result.artifacts
    if result.timed_out:
        out["warning"] = "Timeout alcanzado"
    vnc_u = _browser_vnc_url_for_session(session_id)
    if vnc_u:
        out["vnc_url"] = vnc_u
    return json.dumps(out, ensure_ascii=False)


def get_tools(db: Any, schema: str, spec: Any) -> list[Any]:
    del schema
    worker_template_id = getattr(spec, "worker_id", "") or ""

    def _run(
        modo: str,
        consentimiento_usuario: bool,
        tipo_documento: str | None = None,
        numero_documento: str | None = None,
        correo: str | None = None,
        correo_confirmacion: str | None = None,
        session_id: str = "",
        worker_id: str = "",
    ) -> str:
        assert consentimiento_usuario is True
        wid = (worker_id or "").strip() or worker_template_id
        sid = (session_id or "").strip()
        code = build_pqrsd_identificacion_playwright_script(
            modo=modo,
            tipo_documento=(tipo_documento or "").strip(),
            numero_documento=normalize_document_number(numero_documento or ""),
            correo=(correo or "").strip(),
            correo_confirmacion=(correo_confirmacion or "").strip(),
        )
        result = run_in_sandbox(
            db=db,
            llm=None,
            code=code,
            language="python",
            session_id=sid or None,
            original_request="pqrsd_run_identificacion_step1",
            max_retries=1,
            worker_id=wid,
            image_override=_browser_image_name(),
            inject_python_header=False,
        )
        _debug_pqrsd_step1_log(result, session_id=sid)
        return _format_tool_json(result, session_id=sid)

    return [
        StructuredTool.from_function(
            name=TOOL_NAME,
            description=(
                "Ejecuta en el sandbox browser el paso 1 de identificación PQRSD en medellin.gov.co: "
                "elige radicación identificada o anónima, rellena los campos que el usuario ya proporcionó "
                "y pulsa solicitar verificación por correo. Requiere /sandbox on y "
                "consentimiento_usuario=True. No escribe OTP: el usuario lo completa en el portal o VNC. "
                "Parámetros: modo, consentimiento_usuario, tipo_documento, numero_documento, correo, "
                "correo_confirmacion, session_id, worker_id."
            ),
            func=_run,
            args_schema=PqrsdIdentificacionInput,
        )
    ]
