"""Evidencia de regresión: domain_closure obliga esfera UV (anti-caracol) para evolvecode."""

from __future__ import annotations

from pathlib import Path


def _domain_closure_text() -> str:
    root = Path(__file__).resolve().parents[1]
    p = root / "packages/agents/src/duckclaw/forge/templates/Quant-Trader/domain_closure.md"
    return p.read_text(encoding="utf-8")


def test_domain_closure_mandates_sphere_cartesian_for_orbe() -> None:
    """H1/H2: sin estas cadenas el modelo tiende a espirales (caracol)."""
    text = _domain_closure_text()
    assert "const theta = u * 2 * Math.PI" in text
    assert "const phi = v * Math.PI" in text
    assert "Math.sin(phi) * Math.cos(theta)" in text
    assert "Math.sin(phi) * Math.sin(theta)" in text
    assert "Math.cos(phi)" in text
    assert "caracol" in text.lower() or "nautilo" in text.lower()
    assert "Prohibido" in text or "PROHIBIDO" in text
