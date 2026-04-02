# services/api-gateway/core/config.py
from pydantic import AliasChoices, Field, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Configuración de la API
    PROJECT_NAME: str = "DuckClaw API Gateway"
    VERSION: str = "0.0.1"
    
    # Configuración de Redis (REDIS_URL o DUCKCLAW_REDIS_URL en .env)
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"
    
    # Configuración de Seguridad (valores por defecto para desarrollo/local; en producción definir en .env)
    JWT_SECRET: str = "dev-secret-change-in-production"
    N8N_AUTH_KEY: str = "dev-n8n-auth-key"

    # Username del bot para este gateway (menciones War Room, sin @). Acepta TELEGRAM_BOT_USERNAME o DUCKCLAW_TELEGRAM_BOT_USERNAME en .env.
    TELEGRAM_BOT_USERNAME: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_BOT_USERNAME", "DUCKCLAW_TELEGRAM_BOT_USERNAME"),
    )

    # Le dice a Pydantic que lea del archivo .env si existe (útil para desarrollo local)
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

# Instancia global (Singleton)
settings = Settings()