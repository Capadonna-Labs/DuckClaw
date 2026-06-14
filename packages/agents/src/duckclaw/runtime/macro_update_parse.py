"""Parser fly `/macro --update`."""

from __future__ import annotations

import re
from typing import Any


def parse_macro_update_cli(args: str) -> tuple[dict[str, Any] | None, str]:
    """Parsea ``/macro --update REGIMEN_* confidence=0.8 evidence=\"…\"``."""
    a = (args or "").strip()
    if not re.match(r"^--update\b", a, re.I):
        return None, "Uso: /macro --update REGIMEN_* [confidence=0.8] [evidence=\"texto\"]"
    rest_main = re.sub(r"^--update\s+", "", a, flags=re.I).strip()
    if not rest_main:
        return None, "Falta nombre de régimen (p. ej. REGIMEN_HAWKISH)."
    head, _, tail_join = rest_main.partition(" ")
    regime_name = head.strip().upper()
    tail = tail_join.strip()
    if not regime_name.startswith("REGIMEN_"):
        return None, "El régimen debe empezar con REGIMEN_ (p. ej. REGIMEN_RISK_OFF)."
    conf_f = 0.8
    if tail:
        m_c = re.search(r"confidence=([\d.]+)", tail, re.I)
        if m_c:
            try:
                conf_f = max(0.0, min(1.0, float(m_c.group(1))))
            except ValueError:
                conf_f = 0.8
    evidence_s = ""
    m_e = re.search(r'evidence="([^\"]*)"', a)
    if m_e:
        evidence_s = m_e.group(1).strip()
    if not evidence_s:
        evidence_s = "manual /macro fly (sin evidence explícita)"
    return (
        {
            "regime": regime_name,
            "confidence": conf_f,
            "evidence": evidence_s[:4000],
        },
        "",
    )
