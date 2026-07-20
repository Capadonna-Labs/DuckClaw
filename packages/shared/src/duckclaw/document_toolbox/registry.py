"""Canonical document lanes — ingest, extract, author (UTF-8), Word via Report Engine."""

from __future__ import annotations

INGEST_NATIVE_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown", ".txt", ".json", ".csv"})

# MarkItDown: binary/office → plain text only (never generation).
EXTRACT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".xlsx",
        ".xls",
        ".html",
        ".htm",
    }
)

INGEST_SUFFIXES: frozenset[str] = INGEST_NATIVE_SUFFIXES | EXTRACT_SUFFIXES

# UTF-8 author lane only — never fake office/binary with text.encode.
AUTHOR_TEXT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".md",
        ".markdown",
        ".txt",
        ".html",
        ".htm",
        ".json",
        ".csv",
        ".yaml",
        ".yml",
        ".xml",
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".css",
        ".toml",
        ".ini",
        ".log",
    }
)

AUTHOR_BINARY_REJECT_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pdf",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".xlsx",
        ".xls",
        ".zip",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bin",
    }
)

DOCX_TEMPLATE_OUTPUT_SUFFIX = ".docx"


def suffix_lower(path: str) -> str:
    from pathlib import Path

    return Path(path).suffix.lower()


def ingest_lane_for_suffix(suffix: str) -> str:
    ext = suffix.lower()
    if ext in EXTRACT_SUFFIXES:
        return "extract"
    if ext in INGEST_NATIVE_SUFFIXES:
        return "ingest_native"
    return "unsupported"


def is_extract_suffix(suffix: str) -> bool:
    return suffix.lower() in EXTRACT_SUFFIXES


def is_author_text_suffix(suffix: str) -> bool:
    return suffix.lower() in AUTHOR_TEXT_SUFFIXES


def assert_author_text_path(relative_path: str) -> None:
    """Raise ValueError if write_output_document must not write this suffix."""
    from pathlib import Path

    suf = Path(relative_path).suffix.lower()
    if suf in AUTHOR_BINARY_REJECT_SUFFIXES:
        raise ValueError(
            f"write_output_document no escribe binarios ({suf}). "
            "Documentos Word por plantilla: Report Engine "
            "(register_report_template → patch → render_report_instance). "
            "PDF desde el Word: export_docx_to_pdf. "
            "Sin plantilla de usuario: render_docx_template (built-in)."
        )
    if suf not in AUTHOR_TEXT_SUFFIXES:
        allowed = ", ".join(sorted(AUTHOR_TEXT_SUFFIXES))
        raise ValueError(
            f"Extensión no permitida para autoría UTF-8 ({suf or 'sin extensión'}). "
            f"Permitidas: {allowed}."
        )
