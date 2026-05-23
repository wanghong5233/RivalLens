from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    SERVICE_NAME: str = "rivallens-api"
    ENVIRONMENT: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8010
    LOG_LEVEL: str = "INFO"

    DATABASE_URL: str
    DATABASE_URL_SYNC: str

    DOUBAO_EP: str
    DOUBAO_API_KEY: str

    LLM_MODEL_SUMMARIZATION: str | None = None
    LLM_MODEL_RESEARCH: str | None = None
    LLM_MODEL_COMPRESSION: str | None = None
    LLM_MODEL_QA: str | None = None
    LLM_MODEL_WRITER: str | None = None

    LLM_GLOBAL_CONCURRENCY: int = 4
    COLLECTOR_PER_HOST_QPS: int = 1
    COLLECTOR_USER_AGENT: str = "RivalLens-Researcher/0.1"

    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://localhost:5174"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
