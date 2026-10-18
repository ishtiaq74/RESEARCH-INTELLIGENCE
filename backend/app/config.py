"""Application configuration loaded from environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Research Intelligence"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database (populated in later tasks)
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/research_intelligence"

    # CORS: comma-separated list of allowed origins. No wildcard allowed.
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
