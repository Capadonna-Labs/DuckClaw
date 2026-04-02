"""
Escape de texto para Telegram Bot API (MarkdownV2 y HTML).

MarkdownV2 exige escapar muchos caracteres con barra invertida; lo que en
clientes puede percibirse como “mucha barra”. Para salidas largas de agentes se
prefiere parse_mode HTML: solo escapan & < >.
"""

from __future__ import annotations

import re
from typing import Final

# Caracteres reservados en MarkdownV2 (https://core.telegram.org/bots/api#markdownv2-style)
TELEGRAM_MARKDOWN_V2_SPECIAL: Final[tuple[str, ...]] = (
    "\\",
    "_",
    "*",
    "[",
    "]",
    "(",
    ")",
    "~",
    "`",
    ">",
    "#",
    "+",
    "-",
    "=",
    "|",
    "{",
    "}",
    ".",
    "!",
)

TG_USER_MENTION_LINK_RE = re.compile(r"\[[^\]]+\]\(tg://user\?id=\d+\)")

# sendMessage HTML (https://core.telegram.org/bots/api#sendmessage).
# Margen para prefijo [i/n] y ligera expansión al convertir markdown→HTML.
_TELEGRAM_SENDMESSAGE_HTML_BUDGET: Final[int] = 4096 - 96
_MARK = "\uE000"


def escape_telegram_html(text: str) -> str:
    """Escapa texto plano para parse_mode HTML (subset Telegram Bot API)."""
    if not text:
        return ""
    t = str(text)
    t = t.replace("&", "&amp;")
    t = t.replace("<", "&lt;")
    t = t.replace(">", "&gt;")
    return t


def _esc_href_attr(url: str) -> str:
    u = (url or "").strip()
    return u.replace("&", "&amp;").replace('"', "&quot;")


def _expand_markers_and_escape(segment: str, tokens: list[str]) -> str:
    pat = re.compile(re.escape(_MARK) + r"(\d+)" + re.escape(_MARK))
    out: list[str] = []
    last = 0
    for m in pat.finditer(segment):
        out.append(escape_telegram_html(segment[last : m.start()]))
        idx = int(m.group(1))
        out.append(tokens[idx] if 0 <= idx < len(tokens) else m.group(0))
        last = m.end()
    out.append(escape_telegram_html(segment[last:]))
    return "".join(out)


def _split_emphasis_odd_even(parts: list[str], marker: str) -> list[str]:
    if len(parts) < 2 or len(parts) % 2 != 0:
        return parts
    parts[-2] = parts[-2] + marker + parts[-1]
    parts.pop()
    return parts


def _emphasize_segments(marker: str, line: str, tokens: list[str]) -> str:
    parts = line.split(marker)
    parts = _split_emphasis_odd_even(parts, marker)
    out: list[str] = []
    for i, p in enumerate(parts):
        expanded = _expand_markers_and_escape(p, tokens)
        if i % 2 == 1:
            expanded = f"<b>{expanded}</b>"
        out.append(expanded)
    return "".join(out)


def _inline_line_to_telegram_html(line: str) -> str:
    tokens: list[str] = []

    def code_repl(m: re.Match[str]) -> str:
        tokens.append(escape_telegram_html(m.group(1)))
        return f"{_MARK}{len(tokens) - 1}{_MARK}"

    s = re.sub(r"`([^`\n]+)`", code_repl, line)

    def link_repl(m: re.Match[str]) -> str:
        lab, url = m.group(1), (m.group(2) or "").strip()
        if url.startswith(("http://", "https://")) or url.startswith("tg://user?id="):
            tokens.append(f'<a href="{_esc_href_attr(url)}">{escape_telegram_html(lab)}</a>')
            return f"{_MARK}{len(tokens) - 1}{_MARK}"
        return m.group(0)

    s = re.sub(r"\[([^\]]*)\]\(([^)]+)\)", link_repl, s)

    return _emphasize_segments("**", s, tokens)


def _prose_chunk_to_telegram_html(chunk: str) -> str:
    lines = chunk.split("\n")
    out: list[str] = []
    for line in lines:
        st = line.strip()
        if st and re.fullmatch(r"[-*_]{3,}", st):
            out.append("")
            continue
        m = re.match(r"^\s{0,3}#{1,6}\s+(.*)$", line)
        if m:
            inner = (m.group(1) or "").strip()
            out.append(_inline_line_to_telegram_html(inner) if inner else "")
            continue
        out.append(_inline_line_to_telegram_html(line))
    return "\n".join(out)


def llm_markdown_to_telegram_html(text: str) -> str:
    """
    Convierte un subconjunto habitual del Markdown de modelos (** ` ``` enlaces)
    a HTML válido para parse_mode HTML de Telegram (sin barras de MarkdownV2).
    El texto siempre se escapa salvo las entidades generadas aquí.
    """
    if not text:
        return ""
    normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
    segments: list[tuple[str, str]] = []
    pos = 0
    while True:
        start = normalized.find("```", pos)
        if start == -1:
            if pos < len(normalized):
                segments.append(("text", normalized[pos:]))
            break
        if start > pos:
            segments.append(("text", normalized[pos:start]))
        end = normalized.find("```", start + 3)
        if end == -1:
            segments.append(("text", normalized[start:]))
            break
        inner = normalized[start + 3 : end]
        inner = inner.lstrip("\n")
        if inner:
            first_ln, sep, rest = inner.partition("\n")
            cand = first_ln.strip()
            if (
                sep
                and cand
                and len(cand) < 40
                and " " not in cand
                and not cand.startswith("#")
                and "." not in cand
            ):
                inner = rest
        segments.append(("code", inner))
        pos = end + 3

    out: list[str] = []
    for kind, chunk in segments:
        if kind == "code":
            # Texto plano escapado (sin <code>/<pre>); el troceo ya evita partir fences cuando es posible.
            out.append(escape_telegram_html(chunk))
        else:
            out.append(_prose_chunk_to_telegram_html(chunk))
    return "".join(out)


def _markdown_fence_spans(text: str) -> list[tuple[int, int]]:
    """Intervalos [start, end) que cubren cada bloque ```…``` (end exclusivo del cierre)."""
    spans: list[tuple[int, int]] = []
    pos = 0
    n = len(text)
    while pos < n:
        a = text.find("```", pos)
        if a == -1:
            break
        b = text.find("```", a + 3)
        if b == -1:
            spans.append((a, n))
            break
        spans.append((a, b + 3))
        pos = b + 3
    return spans


def _clamp_plain_split_for_fences(plain: str, idx: int) -> int:
    """Evita cortar dentro de un fence; Telegram trunca si el HTML queda mal cerrado en un trozo."""
    if idx <= 0 or idx >= len(plain):
        return idx
    for start, end in _markdown_fence_spans(plain):
        if start >= end:
            continue
        if start < idx < end:
            left = idx - start
            right = end - idx
            snap_left = start
            snap_right = end
            if left < right and snap_left > 0:
                return snap_left
            if snap_right < len(plain):
                return snap_right
            if snap_left > 0:
                return snap_left
            return snap_right
    return idx


def plain_subchunks_for_telegram_html(
    plain: str,
    *,
    budget: int = _TELEGRAM_SENDMESSAGE_HTML_BUDGET,
) -> list[str]:
    """Parte texto plano hasta que llm_markdown_to_telegram_html(parte) no supere ``budget``."""
    if not plain:
        return []
    if len(llm_markdown_to_telegram_html(plain)) <= budget:
        return [plain]
    if len(plain) <= 1:
        return [plain]
    mid = len(plain) // 2
    split_at = mid
    for delta in range(800):
        j = mid - delta
        if j > 0 and plain[j - 1] == "\n":
            split_at = j
            break
        k = mid + delta
        if k < len(plain) and plain[k - 1] == "\n":
            split_at = k
            break
    if split_at <= 0 or split_at >= len(plain):
        split_at = mid
    split_at = _clamp_plain_split_for_fences(plain, split_at)
    if split_at <= 0 or split_at >= len(plain):
        split_at = max(1, min(len(plain) - 1, mid))
        split_at = _clamp_plain_split_for_fences(plain, split_at)
    if split_at <= 0 or split_at >= len(plain):
        split_at = max(1, min(len(plain) - 1, mid))
    return plain_subchunks_for_telegram_html(plain[:split_at], budget=budget) + plain_subchunks_for_telegram_html(
        plain[split_at:], budget=budget
    )


def escape_telegram_markdown_v2(text: str) -> str:
    """Escapa el texto para envío seguro con parse_mode MarkdownV2."""
    if not text:
        return ""
    t = str(text)
    preserved: list[str] = []

    def _stash_link(m: re.Match[str]) -> str:
        preserved.append(m.group(0))
        return f"TGLINKTOKEN{len(preserved)-1}"

    t = TG_USER_MENTION_LINK_RE.sub(_stash_link, t)
    t = t.replace("\\", "\\\\")
    for c in TELEGRAM_MARKDOWN_V2_SPECIAL:
        if c == "\\":
            continue
        t = t.replace(c, "\\" + c)
    for i, raw in enumerate(preserved):
        t = t.replace(f"TGLINKTOKEN{i}", raw)
    return t
