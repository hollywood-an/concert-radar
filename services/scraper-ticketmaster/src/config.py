"""Runtime configuration loaded from the environment and the repo .env file."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Environment-driven settings for the Ticketmaster scraper."""

    model_config = SettingsConfigDict(env_file=(_REPO_ENV_FILE, Path(".env")), extra="ignore")

    ticketmaster_api_key: str = ""
    # Ticketmaster DMA 259 is the Columbus OH market. (The spec says 249, but that
    # is Chicago in Ticketmaster's DMA scheme — verified against the live API.)
    ticketmaster_dma_id: int = 259
    database_url: str = "postgresql+asyncpg://cr:cr_dev@localhost:5433/concertradar"
