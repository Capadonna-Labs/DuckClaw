"""Kiwix offline encyclopedia search (ZIM files on local disk)."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)


class KiwixSearchInput(BaseModel):
    query: str = Field(
        ...,
        description="Consulta en la enciclopedia offline (ZIM/Kiwix). Español preferido.",
    )
    zim: str = Field(
        default="",
        description="Nombre de archivo .zim opcional; vacío = buscar en todos los ZIM del dir.",
    )


def kiwix_cli_available() -> bool:
    if shutil.which("kiwix-search"):
        return True
    # Binarios instalados en storage local (no brew formula)
    for candidate in (
        Path.home() / ".local" / "bin" / "kiwix-search",
        Path("/Users/workstation/DuckClawOffline/bin/kiwix-search"),
        Path((os.environ.get("DUCKCLAW_KIWIX_BIN_DIR") or "").strip() or "/nonexistent")
        / "kiwix-search",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return True
    return False


def _kiwix_search_bin() -> str:
    found = shutil.which("kiwix-search")
    if found:
        return found
    for candidate in (
        Path.home() / ".local" / "bin" / "kiwix-search",
        Path((os.environ.get("DUCKCLAW_KIWIX_BIN_DIR") or "").strip() or "/nonexistent")
        / "kiwix-search",
        Path("/Users/workstation/DuckClawOffline/bin/kiwix-search"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return "kiwix-search"


def _zim_dir_from_config(config: Optional[dict]) -> Path | None:
    from duckclaw.vault_mirror import kiwix_zim_dir, list_zim_files

    cfg = config or {}
    raw = str(cfg.get("zim_dir") or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return kiwix_zim_dir()


def _resolve_zim_targets(config: Optional[dict], zim_name: str) -> list[Path]:
    from duckclaw.vault_mirror import list_zim_files

    root = _zim_dir_from_config(config)
    files = list_zim_files(root)
    name = (zim_name or "").strip()
    if not name:
        return files
    if not name.endswith(".zim"):
        name = f"{name}.zim"
    matched = [p for p in files if p.name == name or p.name.lower() == name.lower()]
    return matched


def _run_kiwix_search(zim_path: Path, query: str, *, max_results: int) -> str:
    cmd = [_kiwix_search_bin(), str(zim_path), query]
    try:
        proc = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except FileNotFoundError:
        return "kiwix-search no está en PATH (brew install kiwix-tools)."
    except subprocess.TimeoutExpired:
        return f"Timeout kiwix-search en {zim_path.name}."
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0 and not out:
        return f"Error kiwix-search ({zim_path.name}): {err or proc.returncode}"
    lines = [ln for ln in out.splitlines() if ln.strip()][: max(1, max_results)]
    if not lines:
        return f"Sin resultados en {zim_path.name}."
    body = "\n".join(f"- {ln}" for ln in lines)
    return f"### {zim_path.name}\n{body}"


def kiwix_search_tool(config: Optional[dict] = None) -> Any | None:
    """StructuredTool ``kiwix_search`` si hay CLI y al menos un ZIM (o dir configurado)."""
    cfg = config or {}
    if cfg.get("kiwix_enabled") is False:
        return None
    if not kiwix_cli_available():
        return None
    root = _zim_dir_from_config(cfg)
    from duckclaw.vault_mirror import list_zim_files

    zims = list_zim_files(root)
    # Registrar aunque aún no haya ZIM: el tool explica cómo poblar el dir
    if root is None:
        return None

    from langchain_core.tools import StructuredTool

    try:
        max_results = int(cfg.get("max_results", 8))
    except (TypeError, ValueError):
        max_results = 8

    def _search(query: str, zim: str = "") -> str:
        q = (query or "").strip()
        if not q:
            return "query vacío."
        targets = _resolve_zim_targets(cfg, zim)
        if not targets:
            return (
                f"No hay archivos .zim en {root}. "
                "Descarga un ZIM desde https://library.kiwix.org hacia DUCKCLAW_KIWIX_ZIM_DIR."
            )
        parts = [_run_kiwix_search(path, q, max_results=max_results) for path in targets]
        return "\n\n".join(parts)

    zim_names = ", ".join(p.name for p in zims) if zims else "(ningún .zim aún)"
    return StructuredTool.from_function(
        _search,
        name="kiwix_search",
        description=(
            "Busca en la enciclopedia offline local (Kiwix/ZIM). "
            "Úsala sin red o para hechos de referencia. "
            f"ZIMs: {zim_names}. Parámetros: query, zim opcional."
        ),
        args_schema=KiwixSearchInput,
    )


def register_kiwix_into_research(
    tools_list: list[Any],
    research_config: Optional[dict] = None,
) -> None:
    """Añade kiwix_search a la lista de tools del skill research."""
    try:
        tool = kiwix_search_tool(research_config)
        if tool:
            tools_list.append(tool)
    except Exception as exc:
        _log.warning("kiwix_search no registrada: %s", exc)
