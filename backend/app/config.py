"""Application configuration loaded from environment variables."""
from __future__ import annotations

from pydantic import field_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Research Intelligence"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database (populated in later tasks)
    database_url: str = "postgresql+asyncpg://user:password@localhost:5432/research_intelligence"

    # CORS: comma-separated list of allowed origins. No wildcard allowed.
    cors_origins: str = "http://localhost:3000"

    @field_validator("cors_origins")
    @classmethod
    def cors_origins_no_wildcard(cls, v: str) -> str:
        """Reject wildcard or empty CORS origins at startup."""
        origins = [o.strip() for o in v.split(",") if o.strip()]
        if not origins:
            raise ValueError(
                "CORS_ORIGINS must not be empty. "
                "Provide at least one explicit origin, e.g. 'http://localhost:3000'."
            )
        if "*" in origins:
            raise ValueError(
                "CORS_ORIGINS must not contain the wildcard '*'. "
                "List explicit origins instead."
            )
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
