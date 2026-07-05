"""Manager fast-path detectors for greeting and capabilities smalltalk."""

from __future__ import annotations

import re

_CAPABILITIES_SMALLTALK = re.compile(
    r"""^[\s¿¡]*(
  qu[eé]\s+puedes\s+hacer(\s+ahora|\s+por\s+m[ií]|\s+por\s+nosotros)? |
  qu[eé]\s+sabes\s+hacer |
  qu[eé]\s+pued(es|as)\s+(lograr|hacer) |
  en\s+qu[eé]\s+puedes\s+ayud(ar|arme) |
  qu[eé]\s+puedes\s+ofrec(er|erme) |
  cu[aá]les\s+son\s+tus\s+capacidades |
  para\s+qu[eé]\s+sirves |
  qu[eé]\s+funciones\s+tienes |
  mu[eé]strame\s+qu[eé]\s+puedes(\s+hacer)? |
  qui[eé]n\s+eres(\s+t[uú])? |
  qui[eé]n\s+soy(\s+yo)? |
  cu[aá]l\s+es\s+mi\s+(identidad|rol|nombre) |
  cu[aá]l\s+es\s+tu\s+(identidad|rol|nombre) |
  what\s+can\s+you\s+do |
  who\s+are\s+you |
  how\s+can\s+you\s+help(\s+me)?
)[\s?!.]*$""",
    re.IGNORECASE | re.VERBOSE,
)


_IDENTITY_MULTI_QUESTION = re.compile(
    r"(qui[eé]n?\s+eres|qui[eé]n?\s+soy|qu[eé]\s+pud?e?(es|as|e)\s+(lograr|hacer)|"
    r"cu[aá]les\s+son\s+tus\s+capacidades|identidad|capacidades|puedes\s+lograr)",
    re.IGNORECASE,
)

_KNOWLEDGE_INVENTORY_SMALLTALK = re.compile(
    r"""(
        base\s+de\s+conocimiento |
        conocimiento\s+(de\s+la\s+)?(plataforma|proyecto) |
        documentos?\s+indexados? |
        (qu[eé]|cu[aá]ntos?)\s+(documentos?|archivos?|fragmentos?) |
        hay\s+(documentos?|archivos?) |
        tienes\s+(documentos?|archivos?) |
        rag\b |
        fuentes?\s+rag |
        fragmentos?\s+indexados?
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def _strip_scope_preamble(text: str) -> str:
    return re.sub(r"\[KNOWLEDGE_SCOPE\].*?\[/KNOWLEDGE_SCOPE\]", "", text or "", flags=re.DOTALL).strip()


# Pedidos de ejemplo meta (sin dataset concreto): no invocar plan + worker
# Nota: ``pued(es|as|a|e)`` cubre «puedes», «puedas», «puede», «pueda» (no usar ``pueda?s?``, que no casa «puedes»).
_CAPABILITIES_EXAMPLE_SMALLTALK = re.compile(
    r"""^[\s¿¡]*(
  d[aá]me\s+(un\s+)?ejemplo(\s+de\s+algo)?\s+que\s+pued(es|as|a|e)\s+hacer |
  d[aá]me\s+un\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  (mu[eé]strame|ens[eé][ñn]ame)\s+(un\s+)?ejemplo(\s+de\s+algo\s+que\s+pued(es|as|a|e)\s+hacer)? |
  (mu[eé]strame|ens[eé][ñn]ame)\s+un\s+ejemplo |
  ejemplo\s+de\s+algo\s+que\s+pued(es|as|a|e)\s+hacer |
  un\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  pued(es|as|a|e)\s+dar(me)?\s+un\s+ejemplo |
  alg[uú]n\s+ejemplo\s+de\s+lo\s+que\s+pued(es|as|a|e)\s+hacer |
  give\s+me\s+an?\s+example(\s+of\s+what\s+you\s+can\s+do)? |
  show\s+me\s+an?\s+example
)[\s?!.]*$""",
    re.IGNORECASE | re.VERBOSE,
)


def _is_capabilities_smalltalk(text: str) -> bool:
    """
    True si el usuario pide capacidades/identidad o un ejemplo genérico, en frase corta,
    sin datos concretos (evita plan LLM + invoke_worker).
    """
    raw = _strip_scope_preamble(text)
    if not raw or raw.startswith("/"):
        return False
    if len(raw) > 220:
        return False
    if re.search(
        r"\b(con|sobre|analiz|datos|tabla|tablas|sql|ventas|csv|duckdb|query|métrica|metrica|grafico|gráfico)\b",
        raw,
        re.I,
    ):
        return False
    hits = len(_IDENTITY_MULTI_QUESTION.findall(raw))
    if hits >= 2:
        return True
    if len(raw) <= 120:
        return bool(_CAPABILITIES_SMALLTALK.match(raw) or _CAPABILITIES_EXAMPLE_SMALLTALK.match(raw))
    return bool(_CAPABILITIES_SMALLTALK.match(raw))


def _is_knowledge_inventory_smalltalk(text: str) -> bool:
    """True si pregunta por inventario RAG (docs/chunks), sin tarea analítica concreta."""
    raw = _strip_scope_preamble(text)
    if not raw or raw.startswith("/"):
        return False
    if len(raw) > 280:
        return False
    if re.search(
        r"\b(analiz|sql|tabla|ventas|csv|query|métrica|metrica|grafico|gráfico|informe\s+sobre)\b",
        raw,
        re.I,
    ):
        return False
    return _KNOWLEDGE_INVENTORY_SMALLTALK.search(raw) is not None
