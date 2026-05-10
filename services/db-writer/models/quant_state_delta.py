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


class IntradayMocAccumMutation(BaseModel):
    """UPSERT en quant_core.intraday_moc_accum (merge superficial de payload)."""

    session_uid: str = Field(..., min_length=4, max_length=128)
    ticker: str = Field(..., min_length=1, max_length=32)
    patch: dict[str, object] = Field(default_factory=dict)
    trading_date: str = Field(
        default="",
        max_length=16,
        description="YYYY-MM-DD COT; vacío = fecha actual server-side en handler",
    )


class SemanticMemoryUpsertMutation(BaseModel):
    """INSERT/UPSERT fila en main.semantic_memory (job Dreamer / ingestión remota)."""

    topic: str = Field(..., min_length=1, max_length=500)
    insight: str = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    source: str = Field(default="dreamer_job", max_length=160)
    table: str = Field(
        default="main.semantic_memory",
        description="Debe ser main.semantic_memory; otros valores se rechazan.",
    )
    memory_id: str = Field(
        default="",
        max_length=64,
        description="UUID opcional para idempotencia ON CONFLICT (id). Vacío = nueva fila.",
    )


class ConversationCompactionMutation(BaseModel):
    """DELETE parametrizado en telegram_conversation por antigüedad (chat_id = tenant Telegram)."""

    days: int = Field(default=7, ge=1, le=3650)
    chat_id: int = Field(..., description="Telegram chat_id (mismo valor que --tenant-id numérico).")
    table: str = Field(
        default="telegram_conversation",
        description="Debe ser telegram_conversation.",
    )


class TradeSignalMutation(BaseModel):
    signal_id: str = Field(..., min_length=8)
    mandate_id: str = Field(..., min_length=8)
    ticker: str = Field(..., min_length=1)
    signal_type: Literal["ENTRY", "EXIT"] = "ENTRY"
    proposed_weight: float = Field(..., ge=0.0, le=100.0)
    sandbox_backtest_cid: str = ""
    human_approved: bool = False
    status: Literal[
        "PENDING_HITL",
        "AWAITING_HITL",
        "EXECUTED",
        "DISCARDED",
        "FAILED",
        "PENDING",
        "CANCELLED",
    ] = "PENDING_HITL"
    rationale: str = ""
    session_uid: str = ""
    strategy_name: str = Field(default="cfd_auto", min_length=1, max_length=64)


class QuantStateDelta(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    delta_type: Literal[
        "MANDATE_UPSERT",
        "INTRADAY_MOC_ACCUM_UPSERT",
        "SEMANTIC_MEMORY_UPSERT",
        "CONVERSATION_COMPACTION",
        "TRADE_SIGNAL_PROPOSED",
        "TRADE_SIGNAL_APPROVED",
        "TRADE_SIGNAL_EXECUTED",
        "TRADE_SIGNAL_DISCARDED",
        "TRADE_SIGNAL_FAILED",
    ]
    user_id: str = Field(..., min_length=1)
    target_db_path: str = Field(..., min_length=1)
    mutation: dict
