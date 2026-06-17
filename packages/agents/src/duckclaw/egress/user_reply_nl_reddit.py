"""Heurísticas Reddit para síntesis NL (listados MCP / Markdown compacto)."""

from __future__ import annotations

import json
import re

_TOOL_BLOCK_HEADER = re.compile(r"^###\s+([a-zA-Z0-9_.-]+)\s*$", re.MULTILINE)


def _combined_tool_blocks_contain_json(s: str) -> bool:
    """
    True si hay bloques ``### nombre_tool`` seguidos de cuerpo JSON (p. ej. salida unida en
    ``set_reply`` cuando MLX emite tools embebidas y se ejecutan varias en un turno).
    """
    if "### " not in s:
        return False
    for m in _TOOL_BLOCK_HEADER.finditer(s):
        rest = s[m.end() :]
        nxt = re.search(r"^\s*###\s+", rest, re.MULTILINE)
        chunk = rest if not nxt else rest[: nxt.start()]
        t = chunk.lstrip()
        if t.startswith("[") or t.startswith("{"):
            return True
    return False


_TOOL_BLOCK_SNAKE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def _combined_tool_blocks_snake_prose(s: str) -> bool:
    """
    True si hay ``### snake_case_tool`` seguido de texto (p. ej. ``fetch_external_snapshot`` + «Estado:…»).
    Sin esto, ``reply_needs_nl_synthesis`` no dispara la 2.ª pasada y el usuario ve el encabezado crudo.
    """
    if "### " not in s:
        return False
    for m in _TOOL_BLOCK_HEADER.finditer(s):
        name = (m.group(1) or "").strip()
        if not _TOOL_BLOCK_SNAKE_NAME.match(name):
            continue
        rest = s[m.end() :]
        nxt = re.search(r"^\s*###\s+", rest, re.MULTILINE)
        chunk = (rest if not nxt else rest[: nxt.start()]).strip()
        if chunk:
            return True
    return False


def _body_looks_like_reddit_mcp_listing_json(s: str) -> bool:
    """
    Listados MCP (subreddit + posts) a menudo van con prefijo de instancia y no pasan el
    ``startswith('{')`` de la heurística JSON pura; si además el JSON está truncado,
    ``json.loads`` falla y el usuario ve el volcado crudo en Telegram.
    """
    if '"posts"' not in s or '"subreddit"' not in s:
        return False
    return bool(re.search(r'"subreddit"\s*:', s) and re.search(r'"posts"\s*:', s))


def _body_looks_like_reddit_compact_listing_markdown(s: str) -> bool:
    """
    Tras ``format_reddit_mcp_reply_if_applicable`` el modelo a veces devuelve solo el Markdown
    compacto (cabecera ``## r/… (Top N posts)`` + viñetas con ``[Enlace](…)``). Eso ya no es JSON
    ni bloque ``### tool_*``, así que sin esta rama ``reply_needs_nl_synthesis`` queda en False y
    el usuario ve el payload en lugar de un resumen + siguientes pasos.
    """
    t = (s or "").strip()
    if "[Enlace](" not in t:
        return False
    if not re.search(r"^##\s+r/[\w.+-]+\s+\(Top\s+\d+\s+posts\)", t, re.MULTILINE | re.IGNORECASE):
        return False
    return "Score:" in t or "*Extracto:*" in t


def _reddit_compact_subreddit_from_header(s: str) -> str:
    m = re.search(r"^##\s+r/([\w.+-]+)\s+\(Top\s+\d+\s+posts\)", (s or "").strip(), re.MULTILINE | re.IGNORECASE)
    return (m.group(1) or "reddit").strip() if m else "reddit"


def _deterministic_reddit_compact_listing_summary(s: str) -> str:
    """
    Resumen sin LLM a partir del listado compacto (títulos + scores). Cubre el caso
    ``DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS=1`` o fallo/echo del modelo en la segunda pasada.
    """
    if not _body_looks_like_reddit_compact_listing_markdown(s):
        return ""
    sub = _reddit_compact_subreddit_from_header(s)
    titles: list[str] = []
    for raw_ln in (s or "").splitlines():
        ln = raw_ln.strip()
        if not ln.startswith("- "):
            continue
        if " (Score:" not in ln:
            continue
        body = ln[2:].strip()
        idx = body.find(" (Score:")
        if idx <= 0:
            continue
        title = body[:idx].strip()
        title = re.sub(r"^\*+", "", title)
        title = re.sub(r"\*+$", "", title).strip()
        if len(title) < 6:
            continue
        if len(title) > 160:
            title = title[:159] + "…"
        titles.append(title)
        if len(titles) >= 6:
            break
    if not titles:
        return ""
    joined = "; ".join(titles[:5])
    if len(titles) > 5:
        joined += "; …"
    return (
        f"En **r/{sub}** los hilos más visibles en el listado hablan de: {joined}.\n\n"
        "**Siguientes pasos**\n"
        "- Abre el **Enlace** de un hilo si quieres el contexto completo en Reddit.\n"
        "- Si buscas un solo post, pega su URL directa y pide «resume solo este»."
    )

