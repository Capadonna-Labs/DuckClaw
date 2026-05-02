"""
Plantilla — transcript FMP → JSON de sentimiento (execute_sandbox_script).

Specs: specs/features/Integración FMP earnings calendario y transcripts (read-only).md

Uso:
- Obtén texto con `get_fmp_earnings_transcript` en el host y pégalo aquí como TRANSCRIPT_TEXT.
- Ejecuta el script en sandbox; imprime solo JSON en stdout (<2 KB).
- Sin DuckDB vault; opcional TextBlob si la imagen lo trae (fallback léxico inglés español rudimentario).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Tuple

# -------------------------------------------------------------------
# INPUT: reemplazar tras fetch en host con get_fmp_earnings_transcript.
# Omitir cualquier línea de cabecera del tool (solo texto de gestión/participantes).
# -------------------------------------------------------------------
TRANSCRIPT_TEXT: str = """
[Pegar texto del transcript Aquí — sin esto sandbox no tiene señal.]
"""


_STOP = frozenset(
    """a an the and or of to in for on with is was are were be been being 
    it its this that these those we our you your they them i me my 
    at as by from into than then so if out up about after before 
    all any both each few more most other such no nor not only same 
    so than too very can will just should could would may might 
    de la el los las un una que en y a por como del al se es lo hay 
    muy más menos también entre sobre""".split()
)

_RISK_PATTERNS: Tuple[Tuple[str, str], ...] = (
    (r"guidance\b", "guidance"),
    (r"supply chain\b", "supply_chain"),
    (r"margins?\s+(?:pressure|compression)", "margin_pressure"),
    (r"macro(?:economic)?", "macro"),
    (r"tariff\b", "tariff"),
    (r"inventory\b", "inventory"),
    (r"covid\b", "covid"),
    (r"lawsuit\b", "lawsuit"),
    (r"investigation\b", "investigation"),
    (r"capex\b", "capex"),
    (r"c.?ap.?ex\b", "capex"),
)


def _split_opening_vs_qna(text: str) -> tuple[str, str]:
    low = text.lower()
    anchors = ("questions and answers", "question-and-answer", "q&a session", "operator:")
    idx = len(text)
    for a in anchors:
        p = low.find(a)
        if p != -1:
            idx = min(idx, p)
    if idx >= len(text) * 0.85:
        cut = max(800, int(len(text) * 0.35))
        return text[:cut], text[cut:]
    return text[:idx], text[idx:]


try:
    from textblob import TextBlob  # type: ignore[import-not-found]
except ImportError:
    TextBlob = None


def _polarity_blob(chunk: str) -> float | None:
    if TextBlob is None or not chunk.strip():
        return None
    try:
        return float(TextBlob(chunk[:60000]).sentiment.polarity)
    except Exception:
        return None


_NEG = frozenset(
    "challenge decline slowdown weak weakness miss miss miss risk risks "
    "uncertain uncertainty pressure pressured headwind contraction lower "
    "cut cuts reduced reduction layoff layoffs litigation worry worried "
    "desafío deterioro deteriorar debilidad riesgo incertidumbre contracción deterioro ".split()
)
_POS = frozenset(
    "strong stronger growth outperform beat raised raise confident confidence "
    "momentum resilient solid tailwind expand expansion record records "
    "fuerte fortaleza crecimiento confianza sólido ".split()
)


def _polarity_lexicon(chunk: str) -> float:
    toks = re.findall(r"[A-Za-záéíóúñÁÉÍÓÚÑ]+", chunk.lower())
    score = 0
    for t in toks:
        if t in _NEG:
            score -= 1
        if t in _POS:
            score += 1
    n = max(len(toks) // 120, 25)
    return max(-1.0, min(1.0, score / float(n)))


def _polarity(chunk: str) -> float:
    b = _polarity_blob(chunk)
    if b is not None:
        return b
    return _polarity_lexicon(chunk)


def _topics(text: str, k: int = 6) -> list[str]:
    toks = [t.lower() for t in re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüña-z]{5,}", text)]
    c = Counter(t for t in toks if t not in _STOP)
    out = []
    seen = set()
    for w, _ in c.most_common(40):
        if w not in seen and len(out) < k:
            seen.add(w)
            out.append(w)
    return out


def _risks(text: str, k: int = 8) -> list[str]:
    low = text.lower()
    hit: list[str] = []
    for pat, label in _RISK_PATTERNS:
        if re.search(pat, low, re.I):
            hit.append(label)
    uniq: list[str] = []
    for h in hit:
        if h not in uniq:
            uniq.append(h)
        if len(uniq) >= k:
            break
    return uniq


def main() -> None:
    t = TRANSCRIPT_TEXT.strip()
    if not t or "[Pegar texto" in t:
        raise SystemExit(
            json.dumps(
                {
                    "error": "TRANSCRIPT_TEXT vacío — pega contenido tras get_fmp_earnings_transcript",
                    "sentiment_score": 0.0,
                    "key_topics": [],
                    "key_risks": [],
                }
            )
        )

    opening, qna = _split_opening_vs_qna(t)
    p_open = _polarity(opening)
    p_qna = _polarity(qna) if qna.strip() else p_open
    blend = round(0.45 * p_open + 0.55 * p_qna, 3)

    out = {
        "sentiment_score": blend,
        "sentiment_sections": {"opening": round(p_open, 3), "qa_rest": round(p_qna, 3)},
        "key_topics": _topics(t),
        "key_risks": _risks(t),
    }
    print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
