"""Pydantic models for SLM evaluation (teacher-student)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ExecuteSLMRequest(BaseModel):
    prompt: str = Field(..., description="Prompt o JSON sintético para inyectar al SLM local.")
    adapter_path: str = Field(
        default="default",
        description="Ruta LoRA; 'default' usa MLX_ADAPTER_PATH del servidor PM2.",
    )
    temperature: float = Field(0.0, description="Temperatura (0.0 = eval determinística).")
    max_tokens: int = Field(256, description="Límite de tokens de salida.")
