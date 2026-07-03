"""Application settings loaded from the environment and the repo .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Runtime configuration for the gateway service."""

    model_config = SettingsConfigDict(env_file=(_REPO_ENV_FILE, Path(".env")), extra="ignore")

    database_url: str = "postgresql+asyncpg://cr:cr_dev@localhost:5433/concertradar"
    jwt_secret: str = "dev-secret-change-in-prod"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 72


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings."""
    return Settings()
