"""Formateo de respuestas y resolución de artefactos para entrega Telegram (polling y webhook)."""

from __future__ import annotations

import json
import re
from pathlib import Path

_ARTIFACT_SEARCH_DIRS = ("output/sandbox/default", "output")


def truncate_at_break(text: str, max_len: int = 600) -> str:
    if not text or len(text) <= max_len:
        return text
    s = text[: max_len + 1]
    for sep in ("\n\n", ".\n", "\n", ". ", " "):
        idx = s.rfind(sep)
        if idx > max_len // 2:
            return text[: idx + len(sep)].strip()
    return text[:max_len].strip()


def _artifact_search_bases() -> tuple[Path, ...]:
    cwd = Path.cwd()
    return (cwd,)


def _resolve_artifact_path(raw: str, *, extensions: tuple[str, ...]) -> str | None:
    m_clean = (raw or "").strip()
    if not m_clean:
        return None
    p = Path(m_clean)
    if p.is_absolute() and p.is_file() and p.suffix.lower() in extensions:
        return str(p.resolve())
    fname = p.name
    for base in _artifact_search_bases():
        for sub in _ARTIFACT_SEARCH_DIRS:
            candidate = (base / sub / fname).resolve()
            if candidate.is_file() and candidate.suffix.lower() in extensions:
                return str(candidate)
        candidate = (base / m_clean).resolve()
        if candidate.is_file() and candidate.suffix.lower() in extensions:
            return str(candidate)
    return None


def _extract_paths_by_extension(text: str, extensions: tuple[str, ...]) -> list[str]:
    if not (text or "").strip():
        return []
    ext_pat = "|".join(re.escape(e.lstrip(".")) for e in extensions)
    pattern = rf"([^\s`\"'<>]+\.(?:{ext_pat}))"
    seen: set[str] = set()
    found: list[str] = []
    for match in re.findall(pattern, text, re.IGNORECASE):
        resolved = _resolve_artifact_path(match, extensions=extensions)
        if resolved and resolved not in seen:
            seen.add(resolved)
            found.append(resolved)
    return found


def extract_image_paths(text: str) -> list[str]:
    return _extract_paths_by_extension(text, (".png", ".jpg", ".jpeg", ".webp"))


def extract_excel_paths(text: str) -> list[str]:
    return _extract_paths_by_extension(text, (".xlsx",))


def _is_export_hashed_md(filename: str) -> bool:
    name = Path(filename).stem
    return bool(re.match(r"^export_[a-f0-9]{8}$", name, re.I))


def extract_markdown_paths(text: str) -> list[str]:
    paths = _extract_paths_by_extension(text, (".md",))
    return [p for p in paths if not _is_export_hashed_md(p)]


def strip_paths_from_reply(text: str) -> str:
    if not (text or "").strip():
        return text or ""
    s = re.sub(
        r"\s*[.;]?\s*(?:El gráfico|La gráfica|El diagrama|La imagen)\s+(?:ha\s+sido\s+)?guardad[oa]\s+en:\s*[^\n]+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s*[.;]?\s*El archivo\s+se\s+ha\s+guardado\s+en:\s*[^\n]+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*[.;]?\s*Archivo\s+(?:Excel|Markdown)?\s*guardado:\s*[^\n]+", "", s, flags=re.IGNORECASE)
    path_kw = ("guardado en", "guardada en", "se ha guardado", "saved in", "saved to", "ruta:", "path:")
    lines = []
    for line in s.split("\n"):
        low = line.strip().lower()
        if "/workspace/output/" in low:
            continue
        if any(k in low for k in path_kw):
            continue
        if any(ext in low for ext in (".png", ".jpg", ".jpeg", ".webp", ".xlsx", ".md")) and ("/" in line or "\\" in line):
            continue
        lines.append(line)
    return re.sub(r"\s{2,}", " ", "\n".join(lines).strip()).strip()


def caption_for_photo(text: str, image_paths: list[str]) -> str:
    del image_paths
    return truncate_at_break(strip_paths_from_reply(text), 600)


def log_polling(msg: str) -> None:
    """Logs sin buffer para PM2 (long polling)."""
    print(msg, flush=True)


def normalize_worker_reply_for_telegram(reply: str) -> str:
    """Quita tokens EOT/JSON crudo de tools antes de enviar al usuario."""
    from duckclaw.integrations.llm_providers import sanitize_worker_reply_text
    from duckclaw.utils.tool_reply import friendly_query_error

    s = sanitize_worker_reply_text(str(reply or ""))
    if s.startswith("{") and '"name"' in s and ("parameters" in s or '"args"' in s):
        return "El asistente está procesando. Si no ves resultado, intenta de nuevo."
    if s.startswith('{"error"') or (s.startswith("{") and '"error"' in s[:20]):
        try:
            data = json.loads(s)
            err = str((data or {}).get("error", ""))
            friendly = friendly_query_error(err)
            if friendly:
                return friendly
            if "Catalog Error" in err or "Table" in err or "does not exist" in err:
                return "Esa tabla no existe. Pregunta por las tablas disponibles."
            return "No se pudo completar la operación."
        except (json.JSONDecodeError, TypeError):
            pass
    return s or ""


def format_reply_for_telegram_html(reply: str, max_len: int = 800) -> str:
    """Convierte markdown del agente a HTML seguro para Telegram."""
    from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html

    if not reply:
        return ""
    html = llm_markdown_to_telegram_html(reply.strip())
    return truncate_at_break(html, max_len) if len(html) > max_len else html
