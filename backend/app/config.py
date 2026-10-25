"""Application configuration loaded from environment variables."""
from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

BACKEND_DIR: Path = Path(__file__).resolve().parent.parent
DATA_DIR: Path = BACKEND_DIR / "data"
DEFAULT_DB_FILE: Path = DATA_DIR / "app.db"
DEFAULT_DATABASE_URL: str = f"sqlite:///{DEFAULT_DB_FILE.as_posix()}"


def ensure_data_dir(target_dir: Path | None = None) -> Path:
    """Ensure that the data directory exists and return its path."""
    d = target_dir if target_dir is not None else DATA_DIR
    d.mkdir(parents=True, exist_ok=True)
    return d


class Settings(BaseSettings):
    app_name: str = "Research Intelligence"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = DEFAULT_DATABASE_URL

    # CORS: comma-separated list of allowed origins. No wildcard allowed.
    # T2: allow_credentials=True requires explicit origins (never wildcard).
    # WHY CREDENTIALS REQUIRE EXPLICIT ORIGINS:
    #   When allow_credentials=True, the browser checks Access-Control-Allow-Origin
    #   and refuses to attach cookies/auth headers if the response value is "*".
    #   Specifying explicit origins is both a browser requirement and a security
    #   control — only listed origins may send credentialed cross-origin requests.
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

    model_config = {
        "env_file": BACKEND_DIR / ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
