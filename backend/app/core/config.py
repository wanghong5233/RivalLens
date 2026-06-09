from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

LLMProviderName = Literal["doubao", "openai", "qwen"]
LLMModelTier = Literal["strong", "balanced", "fast"]

LLM_PROVIDER_NAMES: tuple[str, ...] = ("doubao", "openai", "qwen")


def _clean_optional_string(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _provider_default_model(settings: Settings, provider_name: str) -> str | None:
    if provider_name == "doubao":
        return _clean_optional_string(settings.DOUBAO_MODEL_BALANCED) or _clean_optional_string(
            settings.DOUBAO_EP
        )
    if provider_name == "openai":
        return _clean_optional_string(settings.OPENAI_MODEL_BALANCED) or _clean_optional_string(
            settings.OPENAI_DEFAULT_MODEL
        )
    if provider_name == "qwen":
        return _clean_optional_string(settings.QWEN_MODEL_BALANCED) or _clean_optional_string(
            settings.QWEN_DEFAULT_MODEL
        )
    return None


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
    HTTP_CLIENT_LOG_LEVEL: str = "WARNING"

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

    LLM_ACTIVE_PROVIDER: LLMProviderName = "doubao"
    LLM_PROVIDER_SUMMARIZATION: str | None = None
    LLM_PROVIDER_RESEARCH: str | None = None
    LLM_PROVIDER_COMPRESSION: str | None = None
    LLM_PROVIDER_QA: str | None = None
    LLM_PROVIDER_WRITER: str | None = None

    LLM_TIER_SUMMARIZATION: LLMModelTier = "strong"
    LLM_TIER_RESEARCH: LLMModelTier = "balanced"
    LLM_TIER_COMPRESSION: LLMModelTier = "fast"
    LLM_TIER_QA: LLMModelTier = "balanced"
    LLM_TIER_WRITER: LLMModelTier = "strong"

    DOUBAO_MODEL_STRONG: str | None = None
    DOUBAO_MODEL_BALANCED: str | None = None
    DOUBAO_MODEL_FAST: str | None = None
    OPENAI_MODEL_STRONG: str | None = None
    OPENAI_MODEL_BALANCED: str | None = None
    OPENAI_MODEL_FAST: str | None = None
    QWEN_MODEL_STRONG: str | None = None
    QWEN_MODEL_BALANCED: str | None = None
    QWEN_MODEL_FAST: str | None = None

    LLM_MODEL_SUMMARIZATION: str | None = None
    LLM_MODEL_RESEARCH: str | None = None
    LLM_MODEL_COMPRESSION: str | None = None
    LLM_MODEL_QA: str | None = None
    LLM_MODEL_WRITER: str | None = None

    LLM_GLOBAL_CONCURRENCY: int = 8
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_TIMEOUT_SUMMARIZATION: int = 180
    LLM_TIMEOUT_COMPRESSION: int = 120
    LLM_TIMEOUT_RESEARCH: int = 90
    LLM_TIMEOUT_QA: int = 90
    LLM_TIMEOUT_WRITER: int = 180
    LLM_CONNECT_TIMEOUT_SECONDS: int = 5
    LLM_MAX_TOKENS_SUMMARIZATION: int = 4096
    LLM_MAX_TOKENS_WRITER: int = 8192
    LLM_MAX_TOKENS_COMPRESSION: int = 2048
    LLM_MAX_TOKENS_QA: int = 2048
    LLM_MAX_TOKENS_RESEARCH: int = 2048
    LLM_MAX_RETRIES: int = 2
    LLM_RETRY_BASE_SECONDS: float = 1.0
    LLM_RETRY_CAP_SECONDS: float = 30.0
    LLM_RETRY_WALL_CLOCK_BUDGET_FACTOR: float = 1.15
    LLM_TPM_BUDGET: int = 0
    LLM_JSON_MODE_ENABLED: bool = True
    ORPHAN_RUN_SWEEP_GRACE_SECONDS: int = 300
    COLLECTOR_PER_HOST_QPS: int = 1
    COLLECTOR_USER_AGENT: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    COLLECTOR_FETCH_TAVILY_FALLBACK_ENABLED: bool = True
    COLLECTOR_FETCH_SEARCH_FALLBACK_ENABLED: bool = True
    COLLECTOR_SEARCH_BREADTH_ENABLED: bool = True
    TAVILY_API_KEY: str | None = None
    SERPER_API_KEY: str | None = None
    BOCHA_API_KEY: str | None = None
    BOCHA_BASE_URL: str = "https://api.bochaai.com/v1"
    BOCHA_RERANK_MODEL: str = "gte-rerank"
    RERANK_DROP_THRESHOLD: float = 0.2
    RERANK_COVERAGE_THRESHOLD: float = 0.5
    RERANK_MIN_HIGH_SCORE_PER_DIM: int = 2
    COLLECTOR_OFFLINE_SNAPSHOT_DIR: str = "./data/snapshots"
    COLLECTOR_FETCH_TIMEOUT_S: int = 10
    COLLECTOR_ROBOTS_CACHE_TTL_S: int = 3600
    WRITER_READ_CONCLUSIONS_FROM_TABLE: bool = True
    CURATOR_MIN_COVERAGE_RATE: float = 1.0
    CURATOR_MIN_DIMENSION_COVERAGE_RATE: float = 0.5
    CURATOR_MIN_REPORT_SECTION_COVERAGE_RATE: float = 1.0
    CURATOR_MAX_QA_REJECTION_RATE: float = 0.5

    CORS_ALLOW_ORIGINS: str = "http://localhost:5173,http://localhost:5174"
    DEMO_FIXTURES_DIR: str | None = None

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

        providers = {self.LLM_ACTIVE_PROVIDER}
        for name, value in (
            ("LLM_PROVIDER_SUMMARIZATION", self.LLM_PROVIDER_SUMMARIZATION),
            ("LLM_PROVIDER_RESEARCH", self.LLM_PROVIDER_RESEARCH),
            ("LLM_PROVIDER_COMPRESSION", self.LLM_PROVIDER_COMPRESSION),
            ("LLM_PROVIDER_QA", self.LLM_PROVIDER_QA),
            ("LLM_PROVIDER_WRITER", self.LLM_PROVIDER_WRITER),
        ):
            provider_name = _clean_optional_string(value)
            if provider_name is None:
                continue
            if provider_name not in LLM_PROVIDER_NAMES:
                raise ValueError(f"{name} must be one of: {', '.join(LLM_PROVIDER_NAMES)}.")
            providers.add(provider_name)

        use_doubao = "doubao" in providers
        use_openai = "openai" in providers
        use_qwen = "qwen" in providers

        if use_doubao:
            if not self.DOUBAO_API_KEY:
                raise ValueError("DOUBAO_API_KEY is required when any LLM slot uses doubao.")
            if not _provider_default_model(self, "doubao"):
                raise ValueError(
                    "DOUBAO_MODEL_BALANCED or DOUBAO_EP is required when any LLM slot uses doubao."
                )
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

        active_default_model = _provider_default_model(self, self.LLM_ACTIVE_PROVIDER)
        if active_default_model is None:
            raise ValueError(
                f"Balanced/default model for LLM_ACTIVE_PROVIDER={self.LLM_ACTIVE_PROVIDER} "
                "is not configured."
            )

        if self.LLM_TIMEOUT_SECONDS <= 0:
            raise ValueError("LLM_TIMEOUT_SECONDS must be positive.")
        for name, value in (
            ("LLM_TIMEOUT_SUMMARIZATION", self.LLM_TIMEOUT_SUMMARIZATION),
            ("LLM_TIMEOUT_COMPRESSION", self.LLM_TIMEOUT_COMPRESSION),
            ("LLM_TIMEOUT_RESEARCH", self.LLM_TIMEOUT_RESEARCH),
            ("LLM_TIMEOUT_QA", self.LLM_TIMEOUT_QA),
            ("LLM_TIMEOUT_WRITER", self.LLM_TIMEOUT_WRITER),
            ("LLM_CONNECT_TIMEOUT_SECONDS", self.LLM_CONNECT_TIMEOUT_SECONDS),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive.")
        for name, value in (
            ("LLM_MAX_TOKENS_SUMMARIZATION", self.LLM_MAX_TOKENS_SUMMARIZATION),
            ("LLM_MAX_TOKENS_WRITER", self.LLM_MAX_TOKENS_WRITER),
            ("LLM_MAX_TOKENS_COMPRESSION", self.LLM_MAX_TOKENS_COMPRESSION),
            ("LLM_MAX_TOKENS_QA", self.LLM_MAX_TOKENS_QA),
            ("LLM_MAX_TOKENS_RESEARCH", self.LLM_MAX_TOKENS_RESEARCH),
        ):
            if value < 0:
                raise ValueError(f"{name} cannot be negative.")
        if self.ORPHAN_RUN_SWEEP_GRACE_SECONDS < 0:
            raise ValueError("ORPHAN_RUN_SWEEP_GRACE_SECONDS cannot be negative.")
        if self.LLM_MAX_RETRIES < 0:
            raise ValueError("LLM_MAX_RETRIES cannot be negative.")
        if self.LLM_RETRY_BASE_SECONDS < 0:
            raise ValueError("LLM_RETRY_BASE_SECONDS cannot be negative.")
        if self.LLM_RETRY_CAP_SECONDS < 0:
            raise ValueError("LLM_RETRY_CAP_SECONDS cannot be negative.")
        if self.LLM_RETRY_WALL_CLOCK_BUDGET_FACTOR <= 0:
            raise ValueError("LLM_RETRY_WALL_CLOCK_BUDGET_FACTOR must be positive.")
        if self.LLM_TPM_BUDGET < 0:
            raise ValueError("LLM_TPM_BUDGET cannot be negative.")
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
        if not self.BOCHA_BASE_URL.strip():
            raise ValueError("BOCHA_BASE_URL cannot be empty.")
        if not self.BOCHA_RERANK_MODEL.strip():
            raise ValueError("BOCHA_RERANK_MODEL cannot be empty.")
        for name, value in (
            ("RERANK_DROP_THRESHOLD", self.RERANK_DROP_THRESHOLD),
            ("RERANK_COVERAGE_THRESHOLD", self.RERANK_COVERAGE_THRESHOLD),
        ):
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be between 0 and 1.")
        if self.RERANK_COVERAGE_THRESHOLD < self.RERANK_DROP_THRESHOLD:
            raise ValueError("RERANK_COVERAGE_THRESHOLD must be >= RERANK_DROP_THRESHOLD.")
        if self.RERANK_MIN_HIGH_SCORE_PER_DIM < 0:
            raise ValueError("RERANK_MIN_HIGH_SCORE_PER_DIM cannot be negative.")
        for name, value in (
            ("CURATOR_MIN_COVERAGE_RATE", self.CURATOR_MIN_COVERAGE_RATE),
            ("CURATOR_MIN_DIMENSION_COVERAGE_RATE", self.CURATOR_MIN_DIMENSION_COVERAGE_RATE),
            (
                "CURATOR_MIN_REPORT_SECTION_COVERAGE_RATE",
                self.CURATOR_MIN_REPORT_SECTION_COVERAGE_RATE,
            ),
            ("CURATOR_MAX_QA_REJECTION_RATE", self.CURATOR_MAX_QA_REJECTION_RATE),
        ):
            if value < 0 or value > 1:
                raise ValueError(f"{name} must be between 0 and 1.")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
