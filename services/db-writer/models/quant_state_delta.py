"""DTOs QUANT_TRADER_STATE_DELTA (finance_worker ledger mutations)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TradingMandateMutation(BaseModel):
    mandate_id: str = Field(..., min_length=8)
    source_worker: str = Field(default="finanz", min_length=1)
    asset_class: str = Field(default="EQUITY", min_length=1)
    direction: Literal["LONG", "SHORT", "NEUTRAL"] = "NEUTRAL"
    max_weight_pct: float = Field(default=10.0, ge=0.0, le=100.0)
    status: Literal["PENDING", "ANALYZING", "FULFILLED", "REJECTED"] = "PENDING"


class TradeSignalMutation(BaseModel):
    signal_id: str = Field(..., min_length=8)
    mandate_id: str = Field(..., min_length=8)
    ticker: str = Field(..., min_length=1)
    signal_type: Literal["ENTRY", "EXIT"] = "ENTRY"
    proposed_weight: float = Field(..., ge=0.0, le=100.0)
    sandbox_backtest_cid: str = ""
    human_approved: bool = False
    status: Literal["AWAITING_HITL", "EXECUTED", "DISCARDED"] = "AWAITING_HITL"
    rationale: str = ""


class QuantStateDelta(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    delta_type: Literal[
        "MANDATE_UPSERT",
        "TRADE_SIGNAL_PROPOSED",
        "TRADE_SIGNAL_APPROVED",
        "TRADE_SIGNAL_EXECUTED",
        "TRADE_SIGNAL_DISCARDED",
    ]
    user_id: str = Field(..., min_length=1)
    target_db_path: str = Field(..., min_length=1)
    mutation: dict
