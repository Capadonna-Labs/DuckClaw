"""Catálogo estático de servidores MCP de referencia (modelcontextprotocol/servers)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def load_official_mcp_reference(repo_root: Path) -> dict[str, Any]:
    """Lee config/mcp_official_reference.yaml; devuelve estructura vacía si falta o falla."""
    path = repo_root / "config" / "mcp_official_reference.yaml"
    empty: dict[str, Any] = {
        "source_repo": "https://github.com/modelcontextprotocol/servers",
        "source_label": "modelcontextprotocol/servers",
        "registry_url": "https://registry.modelcontextprotocol.io/",
        "servers": [],
    }
    if not path.is_file():
        return empty
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return empty
        servers_raw = raw.get("servers") or []
        servers: list[dict[str, Any]] = []
        if isinstance(servers_raw, list):
            for item in servers_raw:
                if not isinstance(item, dict):
                    continue
                sid = str(item.get("id") or "").strip()
                if not sid:
                    continue
                servers.append(
                    {
                        "id": sid,
                        "name": str(item.get("name") or sid).strip(),
                        "description": str(item.get("description") or "").strip(),
                        "runtime": str(item.get("runtime") or "npx").strip().lower(),
                        "install": str(item.get("install") or "").strip(),
                        "repo_path": str(item.get("repo_path") or f"src/{sid}").strip(),
                    }
                )
        return {
            "source_repo": str(raw.get("source_repo") or empty["source_repo"]).strip(),
            "source_label": str(raw.get("source_label") or empty["source_label"]).strip(),
            "registry_url": str(raw.get("registry_url") or empty["registry_url"]).strip(),
            "servers": servers,
        }
    except Exception as exc:
        _log.warning("mcp_official_catalog: load %s: %s", path, exc)
        return empty
