"""DTOs VISUAL_STATE_DELTA (main.visual_assets mutations)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class VisualAssetMutation(BaseModel):
    id: str = Field(..., min_length=8)
    prompt: str = Field(..., min_length=1)
    negative_prompt: str = ""
    file_path: str = Field(..., min_length=1)
    aspect_ratio: str = Field(default="1:1", max_length=16)
    prompt_id_comfy: str = ""
    operation: str = Field(default="", max_length=32)
    source_image_path: str = Field(default="", max_length=2048)


class VisualStateDelta(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    delta_type: Literal["VISUAL_ASSET_UPSERT"] = "VISUAL_ASSET_UPSERT"
    user_id: str = Field(..., min_length=1)
    target_db_path: str = Field(..., min_length=1)
    mutation: VisualAssetMutation
