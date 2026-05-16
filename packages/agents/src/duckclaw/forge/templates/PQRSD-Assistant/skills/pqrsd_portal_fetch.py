"""
Lectura HTTP acotada al portal PQRSD / Alcaldía de Medellín (lista blanca de hosts).

Spec: specs/features/agents-axis/PQRSD_ASSISTANT_MEDELLIN.md
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Literal, Optional
from urllib.parse import urlparse

import requests
import yaml
from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_TIMEOUT_SEC = 15
_MAX_TEXT_CHARS = 48_000

# Páginas canónicas (HTTPS).
_CANONICAL_URLS: dict[str, str] = {
    "pqrsd_home": "https://www.medellin.gov.co/es/pqrsd/",
    "tramites_y_servicios": "https://www.medellin.gov.co/es/tramites-y-servicios/",
    "politica_datos": "https://www.medellin.gov.co/es/transparencia/politica-de-tratamientos-de-datos/",
    "sigesh_bomberos": "https://sigesh.medellin.gov.co/",
    "certificado_residencia_entry": "https://www.medellin.gov.co/statements/choice",
}

PageKey = Literal[
    "pqrsd_home",
    "tramites_y_servicios",
    "politica_datos",
    "sigesh_bomberos",
    "certificado_residencia_entry",
]


def _normalize_host(netloc: str) -> str:
    host = (netloc or "").split("@")[-1].strip().lower()
    if ":" in host and host.split(":")[-1].isdigit():
        host = host.rsplit(":", 1)[0]
    return host


def _host_in_allowlist(netloc: str) -> bool:
    h = _normalize_host(netloc)
    if h.startswith("www."):
        h = h[4:]
    return h in {"medellin.gov.co", "sigesh.medellin.gov.co"}


def _final_url_allowed(final_url: str) -> bool:
    p = urlparse(final_url)
    return _host_in_allowlist(p.netloc or "")


def _html_to_text(html: str) -> str:
    if not html:
        return ""
    s = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    s = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _template_dir() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_routing_rows() -> list[dict[str, str]]:
    yaml_path = _template_dir() / "routing_table.yaml"
    try:
        raw = yaml_path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        rows = data.get("rows") if isinstance(data, dict) else None
        if isinstance(rows, list):
            return [r for r in rows if isinstance(r, dict)]
    except OSError as e:
        logger.warning("pqrsd: no se pudo leer routing_table.yaml: %s", e)
    return []


def pqrsd_fetch_canonical_impl(page: str) -> str:
    """Implementación pura para tests."""
    if page not in _CANONICAL_URLS:
        return json.dumps(
            {"error": "page_key_desconocido", "permitidos": list(_CANONICAL_URLS.keys())},
            ensure_ascii=False,
        )
    url = _CANONICAL_URLS[page]
    try:
        r = requests.get(url, timeout=_TIMEOUT_SEC, allow_redirects=True)
        r.raise_for_status()
    except requests.RequestException as e:
        return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

    final = r.url or url
    if not _final_url_allowed(final):
        return json.dumps(
            {
                "error": "redirect_a_host_no_permitido",
                "solicitado": url,
                "final": final,
            },
            ensure_ascii=False,
        )

    text = _html_to_text(r.text or "")
    if len(text) > _MAX_TEXT_CHARS:
        text = text[:_MAX_TEXT_CHARS] + "\n… [truncado]"

    return json.dumps(
        {
            "page": page,
            "url_solicitada": url,
            "url_final": final,
            "status": r.status_code,
            "text": text,
        },
        ensure_ascii=False,
    )


def pqrsd_entity_routing_impl() -> str:
    rows = _load_routing_rows()
    return json.dumps({"rows": rows}, ensure_ascii=False)


class FetchCanonicalInput(BaseModel):
    page: PageKey = Field(
        ...,
        description=(
            "Clave de página canónica: pqrsd_home, tramites_y_servicios, politica_datos, "
            "sigesh_bomberos (inspección Bomberos), certificado_residencia_entry."
        ),
    )


def get_tools(db: Any, schema: str, spec: Optional[Any] = None) -> list[Any]:
    del db, schema, spec

    def _fetch_canonical(page: str) -> str:
        return pqrsd_fetch_canonical_impl(page)

    fetch_tool = StructuredTool.from_function(
        name="pqrsd_fetch_canonical",
        description=(
            "Descarga texto legible (HTML simplificado) de una página oficial permitida "
            "del portal de la Alcaldía de Medellín o SIGESH. Usar antes de citar contenido "
            "de esas URLs."
        ),
        func=_fetch_canonical,
        args_schema=FetchCanonicalInput,
    )

    routing_tool = StructuredTool.from_function(
        name="pqrsd_entity_routing",
        description=(
            "Devuelve JSON con temas frecuentes y la entidad sugerida cuando el asunto "
            "puede no ser competencia de la Alcaldía de Medellín (tabla orientativa)."
        ),
        func=pqrsd_entity_routing_impl,
    )

    return [fetch_tool, routing_tool]
