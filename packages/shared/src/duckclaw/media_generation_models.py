"""Contratos Pydantic para generacion multimedia via Fal.ai."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

DEFAULT_FLUX_DEV_ENDPOINT = "fal-ai/flux/dev"
DEFAULT_FLUX_PRO_ENDPOINT = "fal-ai/flux-pro/v1.1-ultra"
DEFAULT_FLUX_IMG2IMG_ENDPOINT = "fal-ai/flux/dev/image-to-image"
DEFAULT_FLUX_KONTEXT_PRO_ENDPOINT = "fal-ai/flux-pro/kontext"
DEFAULT_KLING_VIDEO_ENDPOINT = "fal-ai/kling-video/v1.6/standard/text-to-video"
DEFAULT_WAN_ENDPOINT = "fal-ai/wan/v2.2-a14b/text-to-video"

ImageModelEndpoint = Literal[
    "fal-ai/flux/dev",
    "fal-ai/flux-pro/v1.1-ultra",
]
VideoModelEndpoint = Literal[
    "fal-ai/kling-video/v1.6/standard/text-to-video",
    "fal-ai/kling/v2.5/video-to-video",
    "fal-ai/wan/v2.2-a14b/text-to-video",
]
ModelEndpoint = Literal[
    "fal-ai/flux/dev",
    "fal-ai/flux-pro/v1.1-ultra",
    "fal-ai/kling-video/v1.6/standard/text-to-video",
    "fal-ai/kling/v2.5/video-to-video",
    "fal-ai/wan/v2.2-a14b/text-to-video",
]


class MediaGenerationRequest(BaseModel):
    prompt: str = Field(..., description="Prompt descriptivo optimizado para modelos de difusion.")
    model_endpoint: ModelEndpoint = Field(
        DEFAULT_FLUX_DEV_ENDPOINT,
        description="Endpoint del modelo en Fal.ai",
    )
    aspect_ratio: Literal["1:1", "16:9", "9:16"] = "16:9"
    comfy_workflow_json: Optional[dict[str, Any]] = Field(
        None,
        description="Opcional: JSON API de ComfyUI para ejecucion serverless en Fal.",
    )
    duration_sec: float = Field(
        5.0,
        ge=1.0,
        le=30.0,
        description="Duracion estimada del video para costeo Kling/Wan.",
    )


class MediaGenerationResponse(BaseModel):
    success: bool
    media_url: str = Field(default="", description="URL del CDN de Fal.ai con el archivo final.")
    file_path: str = Field(default="", description="Ruta local en artifacts del tenant.")
    latency_sec: float = 0.0
    cost_usd: float = Field(default=0.0, description="Costo estimado debitado de la API.")
    model_endpoint: str = ""
    media_type: Literal["image", "video"] = "image"
    message: str = ""