from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Sentral Ops Private SOP Assistant"
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4.1-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sentral_ops_sops"

    min_source_score: float = 0.22
    max_context_sources: int = 5

    auto_ingest_on_startup: bool = False
    backend_cors_origins: str = "http://localhost:5173"
    data_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "data" / "sentral_ops"
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
