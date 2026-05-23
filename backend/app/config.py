"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    max_upload_mb: int = Field(default=100, ge=1, le=1024)
    conversion_timeout: int = Field(default=600, ge=10)
    storage_dir: Path = Field(default=Path("/tmp/pdf2djvu"))
    storage_ttl_seconds: int = Field(default=3600, ge=60)

    allowed_origins: str = Field(
        default="http://localhost:5173,http://localhost:3000",
        description="Comma-separated list of CORS origins.",
    )

    rate_limit_convert: str = Field(default="30/hour")
    rate_limit_compare: str = Field(default="60/hour")

    ocr_language: str = Field(default="eng")

    # OCR engine selection: "auto" (default — easyocr if GPU available, else tesseract),
    # "tesseract" (force CPU), or "easyocr" (force GPU; falls back to tesseract if missing).
    ocr_engine: str = Field(default="auto")

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
