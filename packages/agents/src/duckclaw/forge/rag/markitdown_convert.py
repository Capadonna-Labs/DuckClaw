"""Convert office/PDF uploads to text via Microsoft MarkItDown (optional dep)."""

from __future__ import annotations

import tempfile
from pathlib import Path

MARKITDOWN_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".html",
        ".htm",
    }
)


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
            "Para PDF/Word instala markitdown en el entorno (uv sync). "
            "Formatos nativos: .md, .txt, .json, .csv."
        ) from exc
    result = MarkItDown().convert(str(path))
    return (result.text_content or "").strip()


def convert_bytes_to_text(*, data: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in MARKITDOWN_SUFFIXES:
        raise ValueError(f"markitdown no soporta extensión: {suffix}")
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        return _convert_path(Path(tmp.name))


def convert_file_path_to_text(path: str | Path) -> str:
    return _convert_path(Path(path).expanduser().resolve())
