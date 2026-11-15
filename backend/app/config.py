"""Application configuration loaded from environment variables."""
from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger("app.config")

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

    # Session cookie security: default True for production (requires HTTPS).
    # In local development (.env) and tests, set to False for plain HTTP.
    session_cookie_secure: bool = True

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
    def cors_origins_validate(cls, v: str) -> str:
        """Validate CORS origins: explicit, http/https, no trailing slash, no path or query."""
        origins = [o.strip() for o in v.split(",") if o.strip()]
        if not origins:
            raise ValueError(
                "CORS_ORIGINS must not be empty. "
                "Provide at least one explicit origin, e.g. 'http://localhost:3000'."
            )
        for origin in origins:
            if "*" in origin:
                raise ValueError(
                    "CORS_ORIGINS must not contain the wildcard '*'. "
                    "List explicit origins instead."
                )
            if not (origin.startswith("http://") or origin.startswith("https://")):
                raise ValueError(
                    f"CORS origin '{origin}' must start with 'http://' or 'https://'."
                )
            if origin.endswith("/"):
                raise ValueError(
                    f"CORS origin '{origin}' must not have a trailing slash."
                )
            parsed = urlsplit(origin)
            if not parsed.netloc:
                raise ValueError(
                    f"CORS origin '{origin}' is missing a valid host/domain."
                )
            if parsed.path:
                raise ValueError(
                    f"CORS origin '{origin}' must not include a path."
                )
            if parsed.query:
                raise ValueError(
                    f"CORS origin '{origin}' must not include a query string."
                )
            if parsed.fragment:
                raise ValueError(
                    f"CORS origin '{origin}' must not include a fragment."
                )
        return v

    @model_validator(mode="after")
    def warn_insecure_cookie_non_localhost(self) -> Settings:
        """Warn when session_cookie_secure is false and origin host is not localhost."""
        if not self.session_cookie_secure:
            for origin in self.cors_origins_list:
                parsed = urlsplit(origin)
                if parsed.hostname != "localhost":
                    logger.warning(
                        "SESSION_COOKIE_SECURE is False, but CORS origin '%s' host is "
                        "not localhost. Plain HTTP cookies to non-localhost origins may be "
                        "intercepted or rejected by browsers.",
                        origin,
                    )
        return self

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    model_config = {
        "env_file": BACKEND_DIR / ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


settings = Settings()
