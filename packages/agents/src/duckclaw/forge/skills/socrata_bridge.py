"""Socrata (SODA) open-data bridge: read-only search and queries over public Socrata portals, no API key.

Manifest: ``skills: [socrata]`` (default portal www.datos.gov.co) or ``socrata: {domains: [www.datos.gov.co, data.cityofnewyork.us]}``.
Only the configured portals are reachable; the model never chooses an arbitrary host.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

DEFAULT_DOMAINS = ("www.datos.gov.co",)
MAX_ROWS = 200
MAX_CHARS = 12000          # every row goes back into the model's context
_DATASET_ID = re.compile(r"^[a-z0-9]{4}-[a-z0-9]{4}$")
EXAMPLES = (
    "Ejemplos en www.datos.gov.co (Colombia, SECOP II, compra pública): jbjy-vk9h contratos electrónicos, "
    "p6dx-8zbt procesos de contratación, qmzu-gj57 proveedores registrados, hgi6-6wh3 proponentes por proceso, cb9c-h8sn adiciones."
)


def _domains(config: Optional[dict]) -> list[str]:
    raw = (config or {}).get("domains") or DEFAULT_DOMAINS
    return [str(d).strip().lower() for d in raw if str(d).strip()]


def _get(url: str, timeout: float = 20.0) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "DuckClaw-socrata"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 host checked against the allowlist
        return json.loads(resp.read().decode("utf-8"))


def _clip(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text if len(text) <= MAX_CHARS else text[:MAX_CHARS] + ' …(recortado: usa $select y un $limit menor)'


def _pick_domain(domain: str, allowed: list[str]) -> str:
    d = (domain or allowed[0]).strip().lower()
    if d not in allowed:
        raise ValueError(f"portal no permitido: {d}; permitidos: {', '.join(allowed)}")
    return d


def socrata_search_impl(query: str, domain: str = "", limit: int = 10, *, allowed: list[str], fetch: Any = None) -> str:
    try:
        d = _pick_domain(domain, allowed)
    except ValueError as exc:
        return str(exc)
    qs = urllib.parse.urlencode({"domains": d, "q": query, "only": "datasets", "limit": max(1, min(int(limit), 25))})
    try:
        data = (fetch or _get)(f"https://api.us.socrata.com/api/catalog/v1?{qs}")
    except Exception as exc:  # noqa: BLE001
        return f"No se pudo buscar en {d} ({type(exc).__name__})."
    rows = [{"id": r["resource"]["id"], "nombre": r["resource"].get("name"), "descripcion": (r["resource"].get("description") or "")[:200],
             "actualizado": (r["resource"].get("updatedAt") or "")[:10], "columnas": (r["resource"].get("columns_field_name") or [])[:40]}
            for r in (data or {}).get("results", []) if isinstance(r, dict) and r.get("resource")]
    return _clip({"portal": d, "datasets": rows})


def socrata_query_impl(dataset_id: str, where: str = "", select: str = "", order: str = "", limit: int = 50, domain: str = "",
                       *, allowed: list[str], fetch: Any = None) -> str:
    try:
        d = _pick_domain(domain, allowed)
    except ValueError as exc:
        return str(exc)
    ds = (dataset_id or "").strip().lower()
    if not _DATASET_ID.match(ds):
        return "dataset_id inválido: debe tener la forma abcd-1234 (usa socrata_search para encontrarlo)."
    params = {"$limit": max(1, min(int(limit), MAX_ROWS))}
    for key, val in (("$where", where), ("$select", select), ("$order", order)):
        if val and val.strip():
            params[key] = val.strip()
    try:
        rows = (fetch or _get)(f"https://{d}/resource/{ds}.json?{urllib.parse.urlencode(params)}")
    except urllib.error.HTTPError as exc:
        return f"Socrata respondió {exc.code}: revisa la sintaxis SoQL de $where/$select/$order o los nombres de columna."
    except Exception as exc:  # noqa: BLE001
        return f"No se pudo consultar {ds} en {d} ({type(exc).__name__})."
    return _clip({"portal": d, "dataset": ds, "filas": len(rows), "datos": rows})


def register_socrata_skill(tools_list: list[Any], socrata_config: Optional[dict] = None) -> None:
    from langchain_core.tools import StructuredTool

    allowed = _domains(socrata_config)

    def _search(query: str, domain: str = "", limit: int = 10) -> str:
        return socrata_search_impl(query, domain, limit, allowed=allowed)

    def _query(dataset_id: str, where: str = "", select: str = "", order: str = "", limit: int = 50, domain: str = "") -> str:
        return socrata_query_impl(dataset_id, where, select, order, limit, domain, allowed=allowed)

    portals = ", ".join(allowed)
    tools_list.append(StructuredTool.from_function(
        _search, name="socrata_search",
        description=f"Busca datasets de datos abiertos en portales Socrata ({portals}): id, nombre, columnas y fecha de actualización. Solo lectura. {EXAMPLES}"))
    tools_list.append(StructuredTool.from_function(
        _query, name="socrata_query",
        description=(f"Consulta filas de un dataset Socrata ({portals}) con SoQL: where (p. ej. \"departamento='Antioquia' AND valor_del_contrato > 100000000\"), "
                     f"select, order, limit (máx. {MAX_ROWS}). Usa select para traer solo las columnas necesarias. Solo lectura. {EXAMPLES}")))
