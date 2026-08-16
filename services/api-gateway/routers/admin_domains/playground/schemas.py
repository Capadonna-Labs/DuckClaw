"""Pydantic bodies y catálogo de proveedores LLM para admin playground."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

LLM_PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "deepseek",
        "label": "DeepSeek (API en la nube)",
        "kind": "api",
        "env_keys": ["DEEPSEEK_API_KEY"],
        "base_url_example": "https://api.deepseek.com/v1",
        "model_example": "deepseek-chat",
        "hint": "Requiere cuenta DeepSeek y API key en .env",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "kind": "api",
        "env_keys": ["OPENAI_API_KEY"],
        "base_url_example": "https://api.openai.com/v1",
        "model_example": "gpt-4o-mini",
        "hint": "ChatGPT / API OpenAI oficial",
    },
    {
        "id": "groq",
        "label": "Groq (API rápida)",
        "kind": "api",
        "env_keys": ["GROQ_API_KEY"],
        "base_url_example": "https://api.groq.com/openai/v1",
        "model_example": "llama-3.3-70b-versatile",
        "hint": "Inferencia en la nube con modelos Llama",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter (proxy unificado)",
        "kind": "api",
        "env_keys": ["OPENROUTER_API_KEY"],
        "base_url_example": "https://openrouter.ai/api/v1",
        "model_example": "z-ai/glm-5.2",
        "hint": "Un endpoint para muchos modelos; default GLM 5.2 (z-ai/glm-5.2)",
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "kind": "api",
        "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "base_url_example": "",
        "model_example": "gemini-2.0-flash",
        "hint": "GOOGLE_API_KEY o GEMINI_API_KEY",
    },
    {
        "id": "anthropic",
        "label": "Anthropic Claude",
        "kind": "api",
        "env_keys": ["ANTHROPIC_API_KEY"],
        "base_url_example": "",
        "model_example": "claude-3-5-haiku-20241022",
        "hint": "API Anthropic",
    },
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "kind": "local",
        "env_keys": [],
        "base_url_example": "http://localhost:11434",
        "model_example": "llama3.2",
        "hint": "Instala Ollama y ejecuta: ollama pull llama3.2",
    },
    {
        "id": "mlx",
        "label": "MLX-Inference (Mac local)",
        "kind": "local",
        "env_keys": [],
        "base_url_example": "http://127.0.0.1:8080/v1",
        "model_example": "",
        "hint": "PM2 MLX-Inference (mlx_lm.server). DUCKCLAW_MLX_BASE_URL o DUCKCLAW_MLX_HOST + MLX_PORT.",
    },
    {
        "id": "huggingface",
        "label": "Hugging Face",
        "kind": "api",
        "env_keys": ["HUGGINGFACE_API_KEY", "HF_TOKEN"],
        "base_url_example": "",
        "model_example": "mistralai/Mistral-7B-Instruct-v0.3",
        "hint": "Token HF en .env",
    },
]


class PlaygroundImageIn(BaseModel):
    mime_type: str = Field(..., max_length=64)
    data_base64: str = Field(..., max_length=20_000_000)


class PlaygroundDocumentIn(BaseModel):
    """Adjunto de documento (PDF/Office/texto) para contexto del turno — no RAG."""

    filename: str = Field(..., min_length=1, max_length=256)
    mime_type: str = Field(default="application/octet-stream", max_length=128)
    data_base64: str = Field(..., min_length=1, max_length=10_000_000)


class PlaygroundModelBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    provider: str = Field(..., min_length=1, max_length=32)
    model: str | None = Field(default=None, max_length=256)
    base_url: str | None = Field(default=None, max_length=512)


class PlaygroundSlmBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    enabled: bool = Field(default=False)
    adapter_path: str | None = Field(
        default=None,
        max_length=512,
        description="Ruta adapter LoRA; vacío usa MLX_ADAPTER_PATH del PM2.",
    )


class PlaygroundVaultBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)
    vault_db_path: str | None = Field(
        default=None,
        max_length=512,
        description="Ruta .duckdb; vacío quita el override por conversación.",
    )


class PlaygroundWorkerBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)
    worker_id: str = Field(..., min_length=1, max_length=64)


class PlaygroundKnowledgeScopeBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)
    knowledge_scope: str = Field(..., min_length=1, max_length=16)
    project_id: str | None = Field(default=None, max_length=64)


class PlaygroundChatBody(BaseModel):
    worker_id: str = Field(default="default", max_length=64)
    message: str = Field(default="", max_length=16000)
    chat_id: str = Field(default="admin-playground", max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    knowledge_scope: str | None = Field(
        default=None,
        max_length=16,
        description="Alcance RAG: platform | project | both",
    )
    telegram_user_id: str | None = Field(
        default=None,
        max_length=32,
        description="ID Telegram para whitelist y equipo /workers (default: DUCKCLAW_OWNER_ID)",
    )
    vault_db_path: str | None = Field(
        default=None,
        max_length=512,
        description="Override DuckDB por conversación (prioridad sobre manifest del worker).",
    )
    images: list[PlaygroundImageIn] = Field(default_factory=list, max_length=15)
    documents: list[PlaygroundDocumentIn] = Field(
        default_factory=list,
        max_length=5,
        description="Documentos del turno (PDF/Office/texto); se extraen a texto, no se indexan en RAG.",
    )
    stream: bool = Field(
        default=False,
        description="Si true, respuesta text/event-stream (tokens SSE + [DONE]).",
    )
    voice_response: bool = Field(
        default=False,
        description="Si true (con stream), sintetiza TTS tras la respuesta y emite evento SSE audio.",
    )
    user_incoming: str | None = Field(
        default=None,
        max_length=16000,
        description="Texto STT original para historial cuando message incluye contexto inyectado (voz en vivo).",
    )

    @model_validator(mode="after")
    def _message_or_attachments(self) -> PlaygroundChatBody:
        if not (self.message or "").strip() and not self.images and not self.documents:
            raise ValueError("message, images o documents requeridos")
        return self


class PlaygroundVoiceBody(BaseModel):
    """Nota de voz → STT → agente → TTS (sin Telegram)."""

    worker_id: str = Field(default="default", max_length=64)
    chat_id: str = Field(default="admin-playground", max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    knowledge_scope: str | None = Field(default=None, max_length=16)
    audio_base64: str = Field(..., min_length=8, description="OGG/WAV/WebM base64 desde el navegador")
    language_hint: str | None = Field(default="es", max_length=16)
    voice_response: bool = Field(
        default=True,
        description="Si true, sintetiza respuesta con TTS (Identity Lock). Si falla, solo texto.",
    )


class PlaygroundChatCancelBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)


class AdminConversationCreateBody(BaseModel):
    title: str | None = None
    section: str | None = None
    worker_id: str | None = None


class AdminConversationPatchBody(BaseModel):
    title: str
