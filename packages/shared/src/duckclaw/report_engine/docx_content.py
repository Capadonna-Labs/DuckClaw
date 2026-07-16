"""Convert section text → docxtpl-safe values (preserve Word tables/cells)."""

from __future__ import annotations

import re
from typing import Any

_MD_TABLE_SEP_RE = re.compile(r"^\s*\|[\s\-:|]+\|\s*$")
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_MD_PIPE_ROW_RE = re.compile(r"^\s*\|.+\|\s*$")


def _normalize_newlines(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


def _markdown_table_rows(lines: list[str], start: int) -> tuple[list[str], int]:
    """Convierte bloque markdown | a | en filas TSV (una línea por fila)."""
    rows: list[str] = []
    i = start
    while i < len(lines) and _MD_PIPE_ROW_RE.match(lines[i]):
        if _MD_TABLE_SEP_RE.match(lines[i]):
            i += 1
            continue
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        rows.append("\t".join(cells))
        i += 1
    return rows, i


def markdown_tables_to_plain(text: str) -> str:
    """
    Tablas markdown → texto tabulado.

    Evita que `| col |` se inyecte literal en celdas Word y rompa el layout.
    """
    lines = _normalize_newlines(text).split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _MD_PIPE_ROW_RE.match(line) and i + 1 < len(lines) and _MD_TABLE_SEP_RE.match(lines[i + 1]):
            table_rows, i = _markdown_table_rows(lines, i)
            if table_rows:
                out.extend(table_rows)
            continue
        if _MD_PIPE_ROW_RE.match(line):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            out.append("\t".join(cells))
            i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def collapse_paragraph_breaks(text: str) -> str:
    """
    docxtpl: saltos de párrafo (\\n\\n) dentro de {{ var }} en celdas pueden
    crear párrafos fuera de la tabla. Mantener solo saltos de línea suaves.
    """
    normalized = _normalize_newlines(text)
    return re.sub(r"\n{2,}", "\n", normalized).strip()


def _markdown_inline_to_richtext(text: str) -> Any:
    from docxtpl import RichText

    rt = RichText()
    pos = 0
    token_re = re.compile(r"(\*\*.+?\*\*)")
    for match in token_re.finditer(text):
        if match.start() > pos:
            chunk = text[pos : match.start()]
            for j, line in enumerate(chunk.split("\n")):
                if j:
                    rt.add("\n")
                if line:
                    rt.add(line)
        token = match.group(0)
        rt.add(token[2:-2], bold=True)
        pos = match.end()
    if pos < len(text):
        tail = text[pos:]
        for j, line in enumerate(tail.split("\n")):
            if j:
                rt.add("\n")
            if line:
                rt.add(line)
    return rt


def _has_markdown_inline(text: str) -> bool:
    return bool(_MD_BOLD_RE.search(text))


def content_to_docxtpl_value(raw: str) -> Any:
    """
    Texto de sección → valor seguro para docxtpl (str o RichText).

    - Tablas markdown → filas tabuladas (no pipes).
    - Párrafos múltiples → saltos de línea suaves (no párrafos Word extra).
    - **negrita** → RichText cuando aplica.
    """
    text = collapse_paragraph_breaks(markdown_tables_to_plain(raw or ""))
    if not text:
        return ""

    if _has_markdown_inline(text):
        return _markdown_inline_to_richtext(text)

    # Multilínea: string con \\n (docxtpl inline en celdas). RichText solo con **negrita**.
    return text
