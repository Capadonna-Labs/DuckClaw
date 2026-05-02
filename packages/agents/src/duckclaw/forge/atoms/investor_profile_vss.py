"""Perfil de inversor desde VSS (main.semantic_memory) — specs MOC Macro PGQ VSS."""

from __future__ import annotations

import os
import re
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pydantic import ValidationError

from duckclaw.forge.models.core_satellite import InvestorProfileModel

PROFILE_QUERIES: list[str] = [
    "tolerancia al riesgo perfil inversión",
    "activos preferidos restricciones portafolio",
    "horizonte temporal objetivo inversión",
    "experiencia trading pérdidas máximas aceptadas",
    "sectores excluidos preferencias ESG",
]

_DEFAULT_PROFILE = InvestorProfileModel()


def _search_semantic_memory_rows(db: Any, query: str, limit: int) -> list[dict[str, Any]]:
    from duckclaw.forge.atoms.semantic_memory_hybrid import search_semantic_memory_hybrid

    q = (query or "").strip()
    if not q:
        return []
    try:
        rows, diag = search_semantic_memory_hybrid(db, q, max(1, min(int(limit), 40)))
        return rows
    except Exception:
        return []


_TICKER_SPLIT = re.compile(r"[,;\s]+")


def parse_profile_from_chunks(chunks_text: list[str], base: InvestorProfileModel) -> InvestorProfileModel:
    """Heurística determinista español/inglés (sin LLM salvo llamada externa)."""
    blob = "\n".join(chunks_text).lower()
    risk = base.risk_tolerance
    if any(k in blob for k in ("agresivo", "aggressive", "alto riesgo", "high risk")):
        risk = "aggressive"
    elif any(k in blob for k in ("conservador", "conservative", "bajo riesgo", "low risk")):
        risk = "conservative"
    md = base.max_drawdown_tolerance
    m_dd = re.search(
        r"(?:drawdown|máximo|maximo|rdd|draw)[^\d]{0,12}(\d{1,2}(?:[.,]\d+)?)\s*%",
        blob,
        re.I,
    )
    if not m_dd:
        m_dd = re.search(r"(\d{1,2}(?:[.,]\d+)?)\s*%\s*(?:mensual|max|drawdown|rdd)", blob, re.I)
    if m_dd:
        try:
            md = float(m_dd.group(1).replace(",", ".")) / 100.0
            md = max(0.0, min(0.5, md))
        except ValueError:
            md = base.max_drawdown_tolerance

    excluded: set[str] = set(x.upper() for x in base.excluded_tickers)
    for neg in ("no invierto", "excluir", "excluded", "no quiero"):
        idx = blob.find(neg)
        if idx == -1:
            continue
        window = blob[idx : idx + 140]
        for tok in _TICKER_SPLIT.split(window):
            t = re.sub(r"[^A-Za-z0-9^-]", "", tok).strip().upper()
            if 1 <= len(t) <= 6 and t.isalpha():
                excluded.add(t)

    sectors = list(base.preferred_sectors)
    if "etf" in blob:
        sectors.append("ETFs")
    horizon = base.time_horizon
    if re.search(r"\b\d+\s*[-–]\s*\d+\s*a[cñ]os", blob):
        horizon = "3-5y"
    exp = base.experience_level
    if "principiante" in blob or "beginner" in blob:
        exp = "beginner"
    elif "avanzado" in blob or "advanced" in blob:
        exp = "advanced"

    return InvestorProfileModel(
        risk_tolerance=risk,
        max_drawdown_tolerance=md,
        excluded_tickers=sorted(excluded),
        preferred_sectors=list(dict.fromkeys(sectors))[:24],
        time_horizon=horizon,
        experience_level=exp,
        raw_chunk_summaries=[c[:420] for c in chunks_text[:12]],
    )


def get_investor_profile(
    db: Any,
    tenant_id: str = "",
    *,
    queries: list[str] | None = None,
    limit_per_query: int = 3,
    timeout_sec: float | None = None,
) -> dict[str, Any]:
    """
    Recupera fragmentos desde VSS y devuelve dict serializable (Pydantic dump).
    `tenant_id` reservado para futura segmentación por filas — hoy solo VSS sobre la bóveda abierta.
    """
    del tenant_id  # tabla actual no aisla por tenant en PK
    import os

    t_out = timeout_sec
    if t_out is None:
        try:
            t_out = float((os.environ.get("DUCKCLAW_MOC_VSS_TIMEOUT_SEC") or "3").strip())
        except ValueError:
            t_out = 3.0
    qs = queries or PROFILE_QUERIES

    def _gather() -> tuple[list[str], list[str]]:
        texts: list[str] = []
        summaries: list[str] = []
        for query in qs:
            rows = _search_semantic_memory_rows(db, query, limit_per_query)
            for row in rows:
                content = str(row.get("content") or "").strip()
                cid = str(row.get("id") or "")
                if content:
                    texts.append(content)
                    summaries.append(f"{cid[:12]}:{content[:280]}")
        return texts, summaries

    if t_out and t_out > 0:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_gather)
            try:
                texts, summaries = fut.result(timeout=t_out)
            except FuturesTimeoutError:
                return _DEFAULT_PROFILE.model_dump()
            except Exception:
                return _DEFAULT_PROFILE.model_dump()
    else:
        texts, summaries = _gather()

    if not texts:
        return _DEFAULT_PROFILE.model_dump()

    parsed = parse_profile_from_chunks(texts, _DEFAULT_PROFILE)
    merged = InvestorProfileModel(
        risk_tolerance=parsed.risk_tolerance,
        max_drawdown_tolerance=parsed.max_drawdown_tolerance,
        excluded_tickers=parsed.excluded_tickers,
        preferred_sectors=parsed.preferred_sectors,
        time_horizon=parsed.time_horizon,
        experience_level=parsed.experience_level,
        raw_chunk_summaries=summaries[:20],
    )

    try:
        InvestorProfileModel.model_validate(merged.model_dump())
    except ValidationError:
        return _DEFAULT_PROFILE.model_dump()
    return merged.model_dump()


def format_profile_summary(profile: dict[str, Any]) -> str:
    p = InvestorProfileModel.model_validate(profile)
    n_chunks = len(p.raw_chunk_summaries)
    prefs = ", ".join(p.preferred_sectors[:8]) if p.preferred_sectors else "(ninguno declarado)"
    excl = ", ".join(p.excluded_tickers[:12]) if p.excluded_tickers else "[]"
    return (
        f"👤 **Perfil (VSS + heurística)**\n\n"
        f"- Tolerancia riesgo: `{p.risk_tolerance}`\n"
        f"- Max drawdown declarado (~): **{p.max_drawdown_tolerance * 100:.1f}%**\n"
        f"- Excluidos: {excl}\n"
        f"- Preferidos / sectores: {prefs}\n"
        f"- Horizonte: `{p.time_horizon}` · Experiencia: `{p.experience_level}`\n"
        f"- Fuentes: **{n_chunks}** snippet(s) en `main.semantic_memory`\n\n"
        "Actualizá contexto con `/context --add` (perfil)."
    )
