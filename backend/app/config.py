"""Application configuration loaded from environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Research Intelligence"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database (populated in later tasks)
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/research_intelligence"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
