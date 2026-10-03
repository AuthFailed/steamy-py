"""Configuration settings for Steam API wrapper."""

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
    RATE_LIMIT_ENABLED: bool = True
    REQUESTS_PER_SECOND: float = 10.0

    model_config = SettingsConfigDict(
        env_prefix="STEAMY_", case_sensitive=False, extra="forbid"
    )
