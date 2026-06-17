from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Query

from routers.admin_domains.admin_common import problem, repo_root, require_admin_key

router = APIRouter(prefix="/catalog", tags=["admin-catalog-meta"])

_CATALOG_STARTER_SKIP = frozenset({"entry_router", "manager_router", "industries"})
_MCP_PORT_ENV_KEY = "DUCKCLAW_MCP_PORT"
_MCP_PORT_DOMAIN = "mcp"
_MCP_PORT_KEY = "port"


def _templates_dir() -> Path:
    from duckclaw.forge import WORKERS_TEMPLATES_DIR

    return WORKERS_TEMPLATES_DIR


def iter_template_ids_for_catalog() -> list[str]:
    from duckclaw.workers.template_registry import list_template_ids

    return list_template_ids()


def manifest_display_fields(template_id: str) -> tuple[str, str]:
    """Nombre y subtítulo desde manifest.yaml (sin listas fijas en código)."""
    import yaml

    manifest = _templates_dir() / template_id / "manifest.yaml"
    name = template_id
    subtitle = f"Plantilla forge/templates/{template_id}"
    if not manifest.is_file():
        return name, subtitle
    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("id") or template_id)
            desc = raw.get("description") or raw.get("subtitle")
            if isinstance(desc, str) and desc.strip():
                subtitle = desc.strip()
    except Exception:
        pass
    return name, subtitle


def catalog_starter_items() -> list[dict[str, str]]:
    """Starters del wizard: solo plantillas presentes en disco."""
    starters: list[dict[str, str]] = []
    for tid in iter_template_ids_for_catalog():
        if tid in _CATALOG_STARTER_SKIP:
            continue
        name, subtitle = manifest_display_fields(tid)
        starters.append({"id": tid, "name": name, "path": tid, "subtitle": subtitle})
    starters.sort(key=lambda x: (x["id"] != "default", str(x.get("name") or x["id"]).lower()))
    return starters


def mcp_port_runtime_setting() -> dict[str, str]:
    """Puerto MCP DB-first con fallback `.env` bootstrap."""
    raw_env = (os.environ.get(_MCP_PORT_ENV_KEY) or "8001").strip() or "8001"
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.admin_runtime_settings import resolve_runtime_setting

        with open_gateway_db(read_only=True) as db:
            resolved = resolve_runtime_setting(
                db,
                tenant_id="global",
                actor_email="",
                domain=_MCP_PORT_DOMAIN,
                key=_MCP_PORT_KEY,
                env_key=_MCP_PORT_ENV_KEY,
                default="8001",
            )
        raw = str(resolved.get("value") or raw_env or "8001").strip() or "8001"
        source = str(resolved.get("source") or ("env" if raw_env else "default"))
    except Exception:
        raw = raw_env
        source = "env" if os.environ.get(_MCP_PORT_ENV_KEY) is not None else "default"
    if not re.fullmatch(r"\d{2,5}", raw):
        raw = "8001"
        source = "default"
    return {"value": raw, "source": source}


async def probe_mcp_http(port: str) -> dict[str, Any]:
    import httpx

    base = f"http://127.0.0.1:{port}"
    out: dict[str, Any] = {"reachable": False, "url": f"{base}/mcp", "port": port}
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            r = await client.get(f"{base}/")
            out["status_code"] = r.status_code
            out["reachable"] = r.status_code < 500
            try:
                body = r.json()
                if isinstance(body, dict):
                    out["service"] = body.get("service")
                    out["hint"] = body.get("hint")
            except Exception:
                pass
    except Exception as exc:
        out["error"] = str(exc)
    return out


@router.get("/source-preview", dependencies=[Depends(require_admin_key)])
async def catalog_source_preview(source_template: str = Query(...)) -> dict[str, Any]:
    src_rel = source_template.strip().strip("/")
    src = _templates_dir() / src_rel
    if not src.is_dir():
        raise problem(404, "Plantilla origen no encontrada", source_template)
    manifest = src / "manifest.yaml"
    skills: list[str] = []
    name = src_rel
    description = ""
    topology = "general"
    if manifest.is_file():
        try:
            import yaml

            raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                name = str(raw.get("name") or src_rel)
                description = str(raw.get("description") or "")
                topology = str(raw.get("topology") or "general")
                sk = raw.get("skills") or []
                if isinstance(sk, list):
                    skills = [str(s) for s in sk]
        except Exception:
            pass
    system_prompt = ""
    soul = ""
    sp_path = src / "system_prompt.md"
    soul_path = src / "soul.md"
    if sp_path.is_file():
        try:
            system_prompt = sp_path.read_text(encoding="utf-8")
        except Exception:
            pass
    if soul_path.is_file():
        try:
            soul = soul_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return {
        "source_template": src_rel,
        "name": name,
        "description": description,
        "topology": topology,
        "skills": skills,
        "system_prompt": system_prompt,
        "soul": soul,
    }


@router.get("/industries", dependencies=[Depends(require_admin_key)])
async def catalog_industries() -> dict[str, Any]:
    industries_dir = _templates_dir() / "industries"
    items: list[dict[str, str]] = []
    if industries_dir.is_dir():
        for d in sorted(industries_dir.iterdir()):
            if d.is_dir() and (d / "manifest.yaml").is_file():
                rel = f"industries/{d.name}"
                name = d.name
                try:
                    import yaml

                    raw = yaml.safe_load((d / "manifest.yaml").read_text(encoding="utf-8")) or {}
                    if isinstance(raw, dict):
                        name = str(raw.get("name") or d.name)
                except Exception:
                    pass
                items.append({"id": rel, "name": name, "path": rel})
    return {"industries": items, "starters": catalog_starter_items()}


@router.get("/topologies", dependencies=[Depends(require_admin_key)])
async def catalog_topologies() -> dict[str, Any]:
    return {
        "topologies": [
            {
                "id": "general",
                "label": "General",
                "description": "Worker autónomo estándar (un agente, un manifest).",
            },
            {
                "id": "orchestrator",
                "label": "Orquestador",
                "description": "Coordina sub-workers vía orchestrator.orchestrates en manifest.yaml.",
            },
        ]
    }


@router.get("/mcp", dependencies=[Depends(require_admin_key)])
async def catalog_mcp() -> dict[str, Any]:
    mcp_port_setting = mcp_port_runtime_setting()
    mcp_port = mcp_port_setting["value"]
    duckclaw_tools = [
        {
            "name": "open_meteo_current_weather",
            "description": "Clima actual por ciudad (Open-Meteo)",
            "server": "duckclaw_mcp",
        },
        {
            "name": "invoke_manager_graph",
            "description": "Fly commands / y grafo Manager (Telegram, workers, team)",
            "server": "duckclaw_mcp",
        },
        {
            "name": "invoke_core_conversation_graph",
            "description": "Grafo core (/status, /balance)",
            "server": "duckclaw_mcp",
        },
        {
            "name": "list_graph_tools",
            "description": "Descubrimiento de capacidades MCP",
            "server": "duckclaw_mcp",
        },
    ]
    stdio_servers: list[dict[str, Any]] = []
    cfg_path = repo_root() / "config" / "mcp_servers.yaml"
    if cfg_path.is_file():
        try:
            import yaml

            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            servers = raw.get("mcp_servers") or {}
            if isinstance(servers, dict):
                for key, val in servers.items():
                    if isinstance(val, dict):
                        stdio_servers.append(
                            {
                                "id": key,
                                "enabled": bool(val.get("enabled", True)),
                                "note": "stdio vía gateway (ver config/mcp_servers.yaml)",
                            }
                        )
        except Exception:
            pass
    live = await probe_mcp_http(mcp_port)
    from core.mcp_official_catalog import load_official_mcp_reference

    official_reference = load_official_mcp_reference(repo_root())
    return {
        "duckclaw_mcp": {
            "command": "uv run python -m duckclaw_mcp --host 0.0.0.0 --port " + mcp_port,
            "url": f"http://127.0.0.1:{mcp_port}/mcp",
            "port": mcp_port,
            "source": mcp_port_setting["source"],
            "runtime_key": "mcp.port",
            "tools": duckclaw_tools,
            "live": live,
        },
        "stdio_servers": stdio_servers,
        "official_reference": official_reference,
        "github_note": "GitHub MCP vía duckclaw.github.mcp_bridge (Docker)",
    }
