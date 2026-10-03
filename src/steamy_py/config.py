"""Configuration settings for Steam API wrapper."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Steam API configuration settings.

    Pass values as keyword arguments (``Settings(MAX_RETRIES=5)``, or the
    lowercase ``max_retries=5``). Fields can also come from environment
    variables with the ``STEAMY_`` prefix (``STEAMY_MAX_RETRIES=5``); no
    ``.env`` file is read. Unknown names raise a ``ValidationError``.
    """

    # Steam API Configuration
    STEAM_API_BASE_URL: str = "https://api.steampowered.com"
    STEAM_STORE_BASE_URL: str = "https://store.steampowered.com/api"
    STEAM_COMMUNITY_BASE_URL: str = "https://steamcommunity.com"

    # Request Configuration
    REQUEST_TIMEOUT: float = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0
    # Longest wait between two attempts. A longer Retry-After (or backoff) is
    # not waited out; the error is raised instead (RateLimitError carries
    # ``retry_after``).
    MAX_RETRY_WAIT: float = 60.0
    # Maximum simultaneous connections of the client's own session.
    CONNECTION_LIMIT: int = 100

    # Rate Limiting
    # Client-side limits per Steam host: requests per second, and how many
    # requests may go out back to back after an idle period (burst). Steam
    # allows 100,000 Web API calls a day per key (~1.16/s), about 200 store
    # requests per 5 minutes per IP, and far fewer on steamcommunity.com.
    RATE_LIMIT_ENABLED: bool = True
    API_REQUESTS_PER_SECOND: float = Field(1.0, gt=0)
    API_BURST: int = Field(10, ge=1)
    STORE_REQUESTS_PER_SECOND: float = Field(0.5, gt=0)
    STORE_BURST: int = Field(10, ge=1)
    COMMUNITY_REQUESTS_PER_SECOND: float = Field(0.25, gt=0)
    COMMUNITY_BURST: int = Field(5, ge=1)
    # Requests that carry the Web API key per UTC day; None for no limit.
    # Once used up, requests with the key raise RateLimitError unsent.
    API_KEY_DAILY_LIMIT: int | None = Field(None, ge=0)

    model_config = SettingsConfigDict(
        env_prefix="STEAMY_", case_sensitive=False, extra="forbid"
    )
