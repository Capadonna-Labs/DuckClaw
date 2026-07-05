# services/db-writer/core/config.py
from __future__ import annotations

import os
from pathlib import Path
from typing import Self

from pydantic import AliasChoices, Field, RedisDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raíz del monorepo (core -> db-writer -> services -> duckclaw)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent


class Settings(BaseSettings):
    PROJECT_NAME: str = "DuckClaw DB Writer"
    REDIS_URL: RedisDsn = Field(
        default="redis://localhost:6379/0",
        validation_alias=AliasChoices("REDIS_URL", "DUCKCLAW_REDIS_URL"),
    )
    QUEUE_NAME: str = "duckdb_write_queue"
    CONTEXT_INJECTION_QUEUE_NAME: str = Field(
        default="duckclaw:state_delta:context",
        validation_alias=AliasChoices(
            "CONTEXT_INJECTION_QUEUE_NAME",
            "DUCKCLAW_CONTEXT_STATE_DELTA_QUEUE",
        ),
    )
    VISUAL_STATE_DELTA_QUEUE_NAME: str = Field(
        default="duckclaw:state_delta:visual",
        validation_alias=AliasChoices(
            "VISUAL_STATE_DELTA_QUEUE_NAME",
            "DUCKCLAW_VISUAL_STATE_DELTA_QUEUE",
        ),
    )
    MEDITATE_STATE_DELTA_QUEUE_NAME: str = Field(
        default="duckclaw:state_delta:meditate",
        validation_alias=AliasChoices(
            "MEDITATE_STATE_DELTA_QUEUE_NAME",
            "DUCKCLAW_MEDITATE_STATE_DELTA_QUEUE",
        ),
    )
    REPORTS_STATE_DELTA_QUEUE_NAME: str = Field(
        default="duckclaw:state_delta:reports",
        validation_alias=AliasChoices(
            "REPORTS_STATE_DELTA_QUEUE_NAME",
            "DUCKCLAW_REPORTS_STATE_DELTA_QUEUE",
        ),
    )
    VLM_STATE_DELTA_QUEUE_NAME: str = Field(
        default="duckclaw:state_delta:vlm",
        validation_alias=AliasChoices(
            "VLM_STATE_DELTA_QUEUE_NAME",
            "DUCKCLAW_VLM_STATE_DELTA_QUEUE",
        ),
    )
    NEEDS_EMBEDDING_QUEUE_NAME: str = "duckclaw:needs_embedding"
    # DLQ: cada cola de state-delta usa ``{QUEUE_NAME}{DLQ_KEY_SUFFIX}`` (default ``:dlq``).
    # Ej.: duckclaw:state_delta:context → duckclaw:state_delta:context:dlq
    DLQ_KEY_SUFFIX: str = ":dlq"
    # Cola reliable: BRPOPLPUSH mueve a ``{QUEUE}{PROCESSING_KEY_SUFFIX}`` hasta ACK.
    PROCESSING_KEY_SUFFIX: str = ":processing"
    PROCESSING_LEASE_SEC: int = 120
    PROCESSING_RECLAIM_INTERVAL_SEC: int = 30

    # Resuelto en validator vía duckclaw.gateway_db (misma bóveda que el Gateway).
    DUCKDB_PATH: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="after")
    def _resolve_duckdb_path(self) -> Self:
        os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(ROOT_DIR))
        from duckclaw.gateway_db import get_gateway_db_path

        object.__setattr__(self, "DUCKDB_PATH", get_gateway_db_path())
        return self


settings = Settings()