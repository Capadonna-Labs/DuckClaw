"""Tests PGQ macro + perfil VSS + válvula MOC v2."""

from __future__ import annotations

import duckdb
import pytest

from duckclaw import DuckClaw
from duckclaw.forge.atoms.investor_profile_vss import parse_profile_from_chunks
from duckclaw.forge.atoms.macro_fly_parse import parse_macro_update_cli
from duckclaw.forge.atoms.macro_pgq_seed import ensure_macro_pgq_seed
from duckclaw.forge.atoms.macro_regime_detector import detect_current_regime
from duckclaw.forge.atoms.moc_allocation_v2 import calculate_target_allocation_v2


def test_parse_macro_update_cli_ok() -> None:
    parsed, err = parse_macro_update_cli('--update REGIMEN_HAWKISH confidence=0.9 evidence="Fed hawkish"')
    assert not err and parsed is not None
    assert parsed["regime"] == "REGIMEN_HAWKISH"
    assert abs(float(parsed["confidence"]) - 0.9) < 1e-6
    assert "Fed hawkish" in parsed["evidence"]


def test_parse_macro_update_cli_rejects_bad_name() -> None:
    parsed, err = parse_macro_update_cli("--update HAWKISH")
    assert parsed is None
    assert "REGIMEN_" in err


def test_parse_profile_from_chunks_drawdown() -> None:
    from duckclaw.forge.models.core_satellite import InvestorProfileModel

    base = InvestorProfileModel()
    out = parse_profile_from_chunks(["tolero máximo 5% drawdown mensual"], base)
    assert pytest.approx(out.max_drawdown_tolerance) == pytest.approx(0.05)


def test_allocation_v2_skip_excluded() -> None:
    regime = {
        "regime": "REGIMEN_RISK_OFF",
        "confidence": 0.9,
        "coherent_assets": ["SHY"],
        "contraindicated_assets": ["META"],
    }
    profile = {"risk_tolerance": "medium", "excluded_tickers": ["SPY"], "max_drawdown_tolerance": 0.05}
    out = calculate_target_allocation_v2(
        ticker="SPY",
        fase_fluido="GAS",
        hrp_weight_capped=0.25,
        equity=50_000.0,
        posicion_actual_usd=0.0,
        regime=regime,
        investor_profile=profile,
    )
    assert out["action"] == "SKIP"


def test_allocation_v2_neutral_unknown_regime_no_penalty() -> None:
    regime = {"regime": "DESCONOCIDO", "confidence": 0.0, "coherent_assets": [], "contraindicated_assets": []}
    profile = {"risk_tolerance": "medium", "excluded_tickers": []}
    out = calculate_target_allocation_v2(
        ticker="QQQ",
        fase_fluido="LIQUID",
        hrp_weight_capped=0.5,
        equity=80_000.0,
        posicion_actual_usd=20_000.0,
        regime=regime,
        investor_profile=profile,
    )
    assert out["macro_penalty"] == 1.0
    assert out["macro_bonus"] == 1.0


@pytest.fixture()
def seeded_macro_db_path(tmp_path):
    """Ruta DuckDB tras seed PGQ — sin DuckClaw viviente para permitir escrituras RW en tests."""
    dbf = tmp_path / "vault.duckdb"
    path = str(dbf)
    con = duckdb.connect(path)
    ensure_macro_pgq_seed(con)
    con.close()
    return path


def test_query_graph_coherent_assets(seeded_macro_db_path) -> None:
    db = DuckClaw(seeded_macro_db_path, read_only=True)
    from duckclaw.forge.atoms.macro_regime_detector import query_pgq_assets_for_regime

    coh = query_pgq_assets_for_regime(db, "REGIMEN_RISK_OFF", ["REFUGIO_DURANTE", "BENEFICIADO_POR"], 0.6)
    assert "SHY" in coh
    assert "XLU" in coh


def test_detect_manual_override_reads_singleton(seeded_macro_db_path) -> None:
    con = duckdb.connect(seeded_macro_db_path)
    con.execute(
        "DELETE FROM quant_core.macro_manual_state WHERE id = 'singleton'",
    )
    con.execute(
        "INSERT INTO quant_core.macro_manual_state (id, regime_override, confidence, evidence) "
        "VALUES ('singleton', 'REGIMEN_HAWKISH', 0.95, 'test')",
    )
    con.close()
    db = DuckClaw(seeded_macro_db_path, read_only=True)
    snap = detect_current_regime(db, "default")
    assert snap["regime"] == "REGIMEN_HAWKISH"
    assert snap["manual_override"] is True
    assert snap["confidence"] >= 0.9
