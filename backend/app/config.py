from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, resolved from this file so it works from any working directory.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
DEFAULT_ORIGINS = "http://localhost:5173,http://localhost:3000"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_expires_seconds: int = 8 * 60 * 60
    reset_token_minutes: int = 30
    # Base of the reset link written to the console until email sending exists.
    frontend_url: str = "http://localhost:5173"
    # Browser origins allowed by CORS, comma separated (FRONTEND_ORIGINS). CORS_ORIGINS is the old name, still read
    # when FRONTEND_ORIGINS is not set.
    frontend_origins: str | None = None
    cors_origins: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        """Origins are compared exactly by browsers, so a trailing slash (`https://app.example.com/`) is dropped."""
        raw = self.frontend_origins or self.cors_origins or DEFAULT_ORIGINS
        return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment / .env
