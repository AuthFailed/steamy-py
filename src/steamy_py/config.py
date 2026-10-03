"""Configuration settings for Steam API wrapper."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Steam API configuration settings."""

    # Steam API Configuration
    STEAM_API_BASE_URL: str = "https://api.steampowered.com"
    STEAM_STORE_BASE_URL: str = "https://store.steampowered.com/api"
    STEAM_COMMUNITY_BASE_URL: str = "https://steamcommunity.com"

    # Request Configuration
    REQUEST_TIMEOUT: int = 30
    MAX_RETRIES: int = 3
    RETRY_DELAY: float = 1.0

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    REQUESTS_PER_SECOND: float = 10.0

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )
