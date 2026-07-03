"""Runtime configuration loaded from the environment and the repo .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Environment-driven settings for the Ticketmaster scraper."""

    model_config = SettingsConfigDict(env_file=(_REPO_ENV_FILE, Path(".env")), extra="ignore")

    ticketmaster_api_key: str = ""
    ticketmaster_dma_id: int = 249
    database_url: str = "postgresql+asyncpg://cr:cr_dev@localhost:5433/concertradar"
