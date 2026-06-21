"""MarkItDown extraction lane — binary documents to plain text only."""

from __future__ import annotations

import tempfile
from pathlib import Path

from duckclaw.document_toolbox.registry import EXTRACT_SUFFIXES, INGEST_NATIVE_SUFFIXES


def markitdown_available() -> bool:
    try:
        import markitdown  # noqa: F401

        return True
    except ImportError:
        return False


def _convert_path(path: Path) -> str:
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise ValueError(
            "MarkItDown no instalado. Ejecuta: uv sync (o duckops up)"
        ) from exc
    result = MarkItDown().convert(str(path))
    return (result.text_content or "").strip()


def convert_bytes_to_text(*, data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in EXTRACT_SUFFIXES:
        raise ValueError(f"MarkItDown solo admite: {', '.join(sorted(EXTRACT_SUFFIXES))}")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        return _convert_path(Path(tmp.name))


def convert_file_path_to_text(path: str | Path) -> str:
    target = Path(path).expanduser().resolve()
    suffix = target.suffix.lower()
    if suffix in INGEST_NATIVE_SUFFIXES:
        return target.read_text(encoding="utf-8", errors="replace").strip()
    if suffix not in EXTRACT_SUFFIXES:
        raise ValueError(f"extract_document_text no admite extensión: {suffix}")
    return _convert_path(target)


def extract_document_text_from_path(path: str | Path) -> tuple[str, str]:
    """Return (text, mime_hint)."""
    target = Path(path).expanduser().resolve()
    if not target.is_file():
        raise ValueError(f"No existe el archivo: {target.name}")
    text = convert_file_path_to_text(target)
    if not text.strip():
        raise ValueError(f"No se extrajo texto de: {target.name}")
    suffix = target.suffix.lower()
    if suffix in EXTRACT_SUFFIXES:
        return text, "text/plain"
    if suffix in {".md", ".markdown"}:
        return text, "text/markdown"
    return text, "text/plain"
