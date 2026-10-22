from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Axelyn"
    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_chat_model: str = "gpt-6-luna"
    openai_reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "none"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536

    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "sentral_ops_sops"

    min_source_score: float = 0.22

    r2_endpoint: str | None = None
    r2_bucket: str | None = None
    r2_access_key_id: str | None = None
    r2_secret_access_key: str | None = None
    r2_prefix: str = "sentral-ops"
    clerk_issuer_url: str | None = None
    clerk_jwt_key: str | None = None
    clerk_authorized_parties: str = ""
    clerk_audience: str | None = None
    max_upload_bytes: int = 10 * 1024 * 1024
    backend_cors_origins: str = "http://localhost:5173"
    harness_db_path: Path = Field(default_factory=lambda: PROJECT_ROOT / "var" / "harness.sqlite3")
    harness_max_turns: int = Field(default=16, ge=1, le=100)
    harness_max_tokens: int = Field(default=32000, ge=1000, le=1000000)
    harness_max_context_chars: int = Field(default=200000, ge=10000, le=2000000)
    harness_max_runtime_seconds: int = Field(default=600, ge=10, le=3600)
    harness_request_timeout_seconds: int = Field(default=60, ge=1, le=120)
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]

    @field_validator("clerk_issuer_url", mode="before")
    @classmethod
    def validate_clerk_issuer(cls, value):
        from urllib.parse import urlsplit

        if not value:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("CLERK_ISSUER_URL must be the HTTPS origin of your Clerk instance.")
        return value.rstrip("/")

    @property
    def authorized_parties(self) -> list[str]:
        return [
            item.strip() for item in self.clerk_authorized_parties.split(",") if item.strip()
        ] or self.cors_origins

    @property
    def storage_configured(self) -> bool:
        return all(
            (self.r2_endpoint, self.r2_bucket, self.r2_access_key_id, self.r2_secret_access_key)
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
