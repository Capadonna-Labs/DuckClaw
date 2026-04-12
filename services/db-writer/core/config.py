# services/db-writer/core/config.py
from pathlib import Path

from pydantic import AliasChoices, Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict

# Calcula la raíz del monorepo (sube 3 niveles: core -> db-writer -> services -> duckclaw)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "DuckClaw DB Writer"
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"
    QUEUE_NAME: str = "duckdb_write_queue"
    CONTEXT_INJECTION_QUEUE_NAME: str = Field(
        default="duckclaw:state_delta:context",
        validation_alias=AliasChoices(
            "CONTEXT_INJECTION_QUEUE_NAME",
            "DUCKCLAW_CONTEXT_STATE_DELTA_QUEUE",
        ),
    )
    NEEDS_EMBEDDING_QUEUE_NAME: str = "duckclaw:needs_embedding"
    
    # Ruta absoluta calculada dinámicamente
    DUCKDB_PATH: str = str(ROOT_DIR / "db" / "duckclaw.duckdb") 

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()