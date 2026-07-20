"""Kiwix offline encyclopedia — search titles + read article body (libzim)."""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from html import unescape
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


class KiwixReadInput(BaseModel):
    title: str = Field(
        ...,
        description=(
            "Título exacto del artículo (como lo devolvió kiwix_search), "
            "p. ej. 'Generación de energía eléctrica' o 'Medellín'."
        ),
    )
    zim: str = Field(
        default="",
        description="Nombre .zim opcional si hay varios.",
    )


def kiwix_cli_available() -> bool:
    if shutil.which("kiwix-search"):
        return True
    for candidate in (
        Path.home() / ".local" / "bin" / "kiwix-search",
        Path("/Users/workstation/DuckClawOffline/bin/kiwix-search"),
        Path((os.environ.get("DUCKCLAW_KIWIX_BIN_DIR") or "").strip() or "/nonexistent")
        / "kiwix-search",
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return True
    return False


def libzim_available() -> bool:
    try:
        from libzim.reader import Archive  # noqa: F401

        return True
    except ImportError:
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
    from duckclaw.vault_mirror import kiwix_zim_dir

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


def _html_to_text(html: str, *, max_chars: int = 12000) -> str:
    text = unescape(html or "")
    text = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<noscript[^>]*>.*?</noscript>", " ", text)
    text = re.sub(r"(?is)<!--.*?-->", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = text.strip()
    if len(text) > max_chars:
        return text[:max_chars].rstrip() + "\n…[truncado]"
    return text


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
        return "kiwix-search no está en PATH."
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
    return (
        f"### {zim_path.name}\n{body}\n\n"
        "_Para el contenido completo usa kiwix_read con el título exacto de la lista._"
    )


def _read_article_from_zim(zim_path: Path, title: str, *, max_chars: int) -> str:
    if not libzim_available():
        return "libzim no instalado (uv sync). No se puede leer el cuerpo del artículo."
    from libzim.reader import Archive

    title_clean = (title or "").strip()
    if not title_clean:
        return "title vacío."
    try:
        archive = Archive(str(zim_path))
    except Exception as exc:
        return f"No se abrió {zim_path.name}: {exc}"

    entry = None
    candidates = [
        title_clean,
        title_clean.replace(" ", "_"),
        f"A/{title_clean.replace(' ', '_')}",
    ]
    for cand in candidates:
        try:
            if archive.has_entry_by_title(cand):
                entry = archive.get_entry_by_title(cand)
                break
        except Exception:
            pass
        try:
            if archive.has_entry_by_path(cand):
                entry = archive.get_entry_by_path(cand)
                break
        except Exception:
            pass
    if entry is None:
        # Fallback: search titles via kiwix-search and try first hit
        hits = _run_kiwix_search(zim_path, title_clean, max_results=3)
        return (
            f"No encontré artículo exacto «{title_clean}» en {zim_path.name}.\n"
            f"Sugerencias de búsqueda:\n{hits}"
        )

    try:
        item = entry.get_item()
        raw = bytes(item.content)
        html = raw.decode("utf-8", errors="replace")
    except Exception as exc:
        return f"Error leyendo ítem «{entry.title}»: {exc}"

    text = _html_to_text(html, max_chars=max_chars)
    if not text:
        return f"Artículo «{entry.title}» sin texto extraíble."
    return f"# {entry.title}\n\nFuente: {zim_path.name} · path={entry.path}\n\n{text}"


def kiwix_search_tool(config: Optional[dict] = None) -> Any | None:
    """StructuredTool ``kiwix_search``."""
    cfg = config or {}
    if cfg.get("kiwix_enabled") is False:
        return None
    if not kiwix_cli_available():
        return None
    root = _zim_dir_from_config(cfg)
    if root is None:
        return None

    from duckclaw.vault_mirror import list_zim_files
    from langchain_core.tools import StructuredTool

    zims = list_zim_files(root)
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
            "Busca TÍTULOS en la enciclopedia offline (Wikipedia ZIM/Kiwix). "
            "No usa RAG ni internet. Tras encontrar títulos, llama kiwix_read "
            "para obtener el texto del artículo. "
            f"ZIMs: {zim_names}."
        ),
        args_schema=KiwixSearchInput,
    )


def kiwix_read_tool(config: Optional[dict] = None) -> Any | None:
    """StructuredTool ``kiwix_read`` — cuerpo del artículo vía libzim."""
    cfg = config or {}
    if cfg.get("kiwix_enabled") is False:
        return None
    if not libzim_available():
        return None
    root = _zim_dir_from_config(cfg)
    if root is None:
        return None

    from langchain_core.tools import StructuredTool

    try:
        max_chars = int(cfg.get("max_chars", 12000))
    except (TypeError, ValueError):
        max_chars = 12000

    def _read(title: str, zim: str = "") -> str:
        targets = _resolve_zim_targets(cfg, zim)
        if not targets:
            return f"No hay .zim en {root}."
        parts: list[str] = []
        for path in targets:
            parts.append(_read_article_from_zim(path, title, max_chars=max_chars))
            # Si ya hay contenido real (empieza con #), no seguir otros ZIM
            if parts[-1].startswith("# "):
                break
        return "\n\n---\n\n".join(parts)

    return StructuredTool.from_function(
        _read,
        name="kiwix_read",
        description=(
            "Lee el texto completo de un artículo de la enciclopedia offline (ZIM). "
            "Pasa el título exacto devuelto por kiwix_search. "
            "Obligatoria cuando el usuario pide explicación o detalle, no solo títulos."
        ),
        args_schema=KiwixReadInput,
    )


def register_kiwix_tools(
    tools_list: list[Any],
    config: Optional[dict] = None,
) -> None:
    """Registra kiwix_search + kiwix_read si hay entorno."""
    try:
        search = kiwix_search_tool(config)
        if search:
            tools_list.append(search)
        read = kiwix_read_tool(config)
        if read:
            tools_list.append(read)
    except Exception as exc:
        _log.warning("kiwix tools no registradas: %s", exc)


def register_kiwix_into_research(
    tools_list: list[Any],
    research_config: Optional[dict] = None,
) -> None:
    """Compat: añade tools Kiwix al skill research."""
    register_kiwix_tools(tools_list, research_config)
