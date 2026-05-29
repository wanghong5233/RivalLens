from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
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
    LANGGRAPH_CHECKPOINT_DSN: str | None = None

    DOUBAO_EP: str | None = None
    DOUBAO_API_KEY: str | None = None
    DOUBAO_BASE_URL: str = "https://ark.cn-beijing.volces.com/api/v3"

    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    OPENAI_DEFAULT_MODEL: str = "gpt-4o-mini"
    QWEN_API_KEY: str | None = None
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_DEFAULT_MODEL: str = "qwen-plus"

    LLM_PROVIDER_SUMMARIZATION: Literal["doubao", "openai", "qwen"] = "doubao"
    LLM_PROVIDER_RESEARCH: Literal["doubao", "openai", "qwen"] = "doubao"
    LLM_PROVIDER_COMPRESSION: Literal["doubao", "openai", "qwen"] = "doubao"
    LLM_PROVIDER_QA: Literal["doubao", "openai", "qwen"] = "doubao"
    LLM_PROVIDER_WRITER: Literal["doubao", "openai", "qwen"] = "doubao"

    LLM_MODEL_SUMMARIZATION: str | None = None
    LLM_MODEL_RESEARCH: str | None = None
    LLM_MODEL_COMPRESSION: str | None = None
    LLM_MODEL_QA: str | None = None
    LLM_MODEL_WRITER: str | None = None

    LLM_GLOBAL_CONCURRENCY: int = 4
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_MAX_RETRIES: int = 2
    COLLECTOR_PER_HOST_QPS: int = 1
    COLLECTOR_USER_AGENT: str = "RivalLens-Researcher/0.1"
    TAVILY_API_KEY: str | None = None
    COLLECTOR_OFFLINE_SNAPSHOT_DIR: str = "./data/snapshots"
    COLLECTOR_FETCH_TIMEOUT_S: int = 10
    COLLECTOR_ROBOTS_CACHE_TTL_S: int = 3600
    WRITER_READ_CONCLUSIONS_FROM_TABLE: bool = True

    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://localhost:5174"

    @model_validator(mode="after")
    def validate_llm_provider_credentials(self) -> Settings:
        if not self.LANGGRAPH_CHECKPOINT_DSN:
            self.LANGGRAPH_CHECKPOINT_DSN = self.DATABASE_URL_SYNC.replace(
                "postgresql+psycopg2://",
                "postgresql://",
            ).replace(
                "postgresql+psycopg://",
                "postgresql://",
            )

        if not self.LANGGRAPH_CHECKPOINT_DSN.startswith("postgresql://"):
            raise ValueError("LANGGRAPH_CHECKPOINT_DSN must use postgresql:// DSN format.")

        providers = (
            self.LLM_PROVIDER_SUMMARIZATION,
            self.LLM_PROVIDER_RESEARCH,
            self.LLM_PROVIDER_COMPRESSION,
            self.LLM_PROVIDER_QA,
            self.LLM_PROVIDER_WRITER,
        )
        use_doubao = any(item == "doubao" for item in providers)
        use_openai = any(item == "openai" for item in providers)
        use_qwen = any(item == "qwen" for item in providers)

        if use_doubao:
            if not self.DOUBAO_API_KEY:
                raise ValueError("DOUBAO_API_KEY is required when any LLM slot uses doubao.")
            if not self.DOUBAO_EP:
                raise ValueError("DOUBAO_EP is required when any LLM slot uses doubao.")
            if not self.DOUBAO_BASE_URL.strip():
                raise ValueError("DOUBAO_BASE_URL cannot be empty.")

        if use_openai:
            if not self.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY is required when any LLM slot uses openai.")
            if not self.OPENAI_DEFAULT_MODEL.strip():
                raise ValueError("OPENAI_DEFAULT_MODEL cannot be empty.")
            if not self.OPENAI_BASE_URL.strip():
                raise ValueError("OPENAI_BASE_URL cannot be empty.")

        if use_qwen:
            if not self.QWEN_API_KEY:
                raise ValueError("QWEN_API_KEY is required when any LLM slot uses qwen.")
            if not self.QWEN_DEFAULT_MODEL.strip():
                raise ValueError("QWEN_DEFAULT_MODEL cannot be empty.")
            if not self.QWEN_BASE_URL.strip():
                raise ValueError("QWEN_BASE_URL cannot be empty.")

        if self.LLM_TIMEOUT_SECONDS <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS must be positive.")
        if self.LLM_MAX_RETRIES < 0:
            raise ValueError("LLM_MAX_RETRIES cannot be negative.")
        if self.LLM_GLOBAL_CONCURRENCY <= 0:
            raise ValueError("LLM_GLOBAL_CONCURRENCY must be positive.")
        if self.COLLECTOR_PER_HOST_QPS <= 0:
            raise ValueError("COLLECTOR_PER_HOST_QPS must be positive.")
        if self.COLLECTOR_FETCH_TIMEOUT_S <= 0:
            raise ValueError("COLLECTOR_FETCH_TIMEOUT_S must be positive.")
        if self.COLLECTOR_ROBOTS_CACHE_TTL_S <= 0:
            raise ValueError("COLLECTOR_ROBOTS_CACHE_TTL_S must be positive.")
        if not self.COLLECTOR_USER_AGENT.strip():
            raise ValueError("COLLECTOR_USER_AGENT cannot be empty.")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
