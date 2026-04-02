"""DTOs CONTEXT_INJECTION (alineados con services/api-gateway/core/context_injection_delta.py)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ContextInjectionMutation(BaseModel):
    raw_text: str = Field(..., min_length=1)
    source: Literal["telegram_cmd"] = "telegram_cmd"


class ContextInjectionStateDelta(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    delta_type: Literal["CONTEXT_INJECTION"] = "CONTEXT_INJECTION"
    mutation: ContextInjectionMutation
    user_id: str = Field(..., min_length=1)
    target_db_path: str = Field(..., min_length=1)
