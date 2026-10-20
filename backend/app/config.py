from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Sentral Ops Private SOP Assistant"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-6-luna"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "none"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sentral_ops_sops"

    min_source_score: float = 0.22
    max_context_sources: int = 5

    auto_ingest_on_startup: bool = False
    r2_endpoint: str | None = None
    r2_bucket: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_prefix: str = "sentral-ops"
    workspace_cookie_secure: bool = False
    max_upload_bytes: int = 10 * 1024 * 1024
    backend_cors_origins: str = "http://localhost:5173"
    data_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "data" / "sentral_ops")

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @property
    def storage_configured(self) -> bool:
        return all(
            (self.r2_endpoint, self.r2_bucket, self.r2_access_key_id, self.r2_secret_access_key)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
