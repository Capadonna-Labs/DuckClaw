"""DTO VLM_CONTEXT_EXTRACTED (Telegram / playground vision enrichment)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VlmContextMutation(BaseModel):
    image_hash: str = Field(..., min_length=8)
    vlm_summary: str = Field(..., min_length=1)
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


class VlmStateDelta(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    delta_type: Literal["VLM_CONTEXT_EXTRACTED"] = "VLM_CONTEXT_EXTRACTED"
    mutation: VlmContextMutation
