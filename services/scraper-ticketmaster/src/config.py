"""Runtime configuration loaded from the environment and the repo .env file."""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    """Environment-driven settings for the Ticketmaster scraper."""

    model_config = SettingsConfigDict(env_file=(_REPO_ENV_FILE, Path(".env")), extra="ignore")

    ticketmaster_api_key: str = ""
    # Ticketmaster DMA 259 is the Columbus OH market. (The spec says 249, but that
    # is Chicago in Ticketmaster's DMA scheme — verified against the live API.)
    ticketmaster_dma_id: int = 259
    kafka_bootstrap_servers: str = "localhost:19092"
    # An empty bucket turns raw-page archiving off.
    s3_bucket: str = ""
    s3_endpoint_url: str | None = None
    # Empty keys defer to boto3's default credential chain, i.e. the instance role on AWS.
    s3_access_key: str = ""
    s3_secret_key: str = ""

    @field_validator("s3_bucket", "s3_access_key", "s3_secret_key")
    @classmethod
    def _blank_placeholder(cls, value: str) -> str:
        """Treat an unfilled `<...>` placeholder as empty, as the enricher does for Spotify."""
        return "" if value.startswith("<") else value

    @field_validator("s3_endpoint_url")
    @classmethod
    def _aws_endpoint_when_blank(cls, value: str | None) -> str | None:
        """Map a blank or placeholder endpoint to None so boto3 resolves the AWS endpoint."""
        return None if not value or value.startswith("<") else value
