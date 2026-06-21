"""Canonical document lanes — single source of truth for ingest, extract, author, convert."""

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

PANDOC_INPUT_SUFFIXES: frozenset[str] = frozenset({".md", ".markdown", ".txt", ".html", ".htm"})
PANDOC_OUTPUT_FORMATS: frozenset[str] = frozenset({"docx", "pdf", "html"})

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


def is_pandoc_input(suffix: str) -> bool:
    return suffix.lower() in PANDOC_INPUT_SUFFIXES
