"""DTOs Core-Satellite HRP / MOC (specs/features/Core-Satellite HRP Weekly + MOC CFD.md)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class HRPMandateRow(BaseModel):
    """Fila lista para UPSERT en ``quant_core.hrp_mandates``."""

    ticker: str = Field(..., min_length=1, max_length=20)
    hrp_weight: float = Field(..., ge=0.0, le=1.0)
    hrp_weight_capped: float = Field(..., ge=0.0, le=1.0)
    lookback_days: int = Field(..., ge=1, le=4000)
    n_observations: int = Field(..., ge=0)
    shrinkage_method: str = Field(default="ledoit_wolf", max_length=50)


class TargetAllocationDict(BaseModel):
    """Contrato estable del resultado de válvula MOC (equiv. dict legacy)."""

    action: Literal["HOLD", "BUY", "SELL"]
    delta_usd: float
    target_weight: Optional[float] = None
    hrp_weight: Optional[float] = None
    valvula: Optional[float] = None
    fase: Optional[str] = None
    rationale: str = ""

    @field_validator("fase", mode="before")
    @classmethod
    def _strip_fase(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    def as_dict(self) -> dict[str, Any]:
        d = self.model_dump(exclude_none=True)
        # Siempre exponer rationale
        if "rationale" not in d:
            d["rationale"] = ""
        return d


class MOCPipelineSignalSummary(BaseModel):
    """Metadatos de una fila para resumen Telegram MOC."""

    ticker: str
    action: str
    delta_usd: float
    hrp_capped_pct: float
    fase: str
    valvula: float


class WeeklyHRPNotice(BaseModel):
    """Cabeceras para notificación HRP semanal."""

    fecha: str
    n_tickers: int
    lookback_days: int
    shrinkage: str
    ticker_max: str
    peso_max: float
    ticker_min: str
    peso_min: float
    computed_at: datetime


class MacroRegimeSnapshot(BaseModel):
    """Estado macro + listas PGQ para MOC v2."""

    regime: str = "DESCONOCIDO"
    vix: Optional[float] = None
    confidence: float = 0.0
    coherent_assets: list[str] = Field(default_factory=list)
    contraindicated_assets: list[str] = Field(default_factory=list)
    macro_context_snippets: list[str] = Field(default_factory=list)
    manual_override: bool = False


class InvestorProfileModel(BaseModel):
    """Perfil inferido desde VSS + heurística (MOC Macro)."""

    risk_tolerance: Literal["conservative", "medium", "aggressive"] = "medium"
    max_drawdown_tolerance: float = Field(default=0.05, ge=0.0, le=1.0)
    excluded_tickers: list[str] = Field(default_factory=list)
    preferred_sectors: list[str] = Field(default_factory=list)
    time_horizon: str = "medium"
    experience_level: str = "intermediate"
    raw_chunk_summaries: list[str] = Field(default_factory=list)


class MOCTargetAllocationV2(BaseModel):
    """Salida válvula MOC con filtros macro y perfil."""

    action: Literal["HOLD", "BUY", "SELL", "SKIP"]
    delta_usd: float
    target_weight: Optional[float] = None
    hrp_weight: Optional[float] = None
    valvula: Optional[float] = None  # alias compat: válvula final
    valvula_base: Optional[float] = None
    valvula_final: Optional[float] = None
    macro_penalty: Optional[float] = None
    macro_bonus: Optional[float] = None
    risk_multiplier: Optional[float] = None
    fase: Optional[str] = None
    regime_tag: Optional[str] = None
    rationale: str = ""

    @field_validator("fase", mode="before")
    @classmethod
    def _strip_fase_v2(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip()
        return v

    def as_dict(self) -> dict[str, Any]:
        d = self.model_dump(exclude_none=True)
        if "rationale" not in d:
            d["rationale"] = ""
        if self.valvula_final is not None and "valvula" not in d:
            d["valvula"] = self.valvula_final
        elif self.valvula is None and self.valvula_final is not None:
            d["valvula"] = self.valvula_final
        return d

