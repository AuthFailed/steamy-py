# Main Steam client
# Core components (for advanced users)
from .client import Client
from .config import Settings

# All exceptions
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    GameNotFoundError,
    InvalidAppIDError,
    InvalidSteamIDError,
    NetworkError,
    PlayerNotFoundError,
    PrivateProfileError,
    RateLimitError,
    ResponseParsingError,
    ServiceUnavailableError,
    SteamAPIError,
)

# Most commonly used models (for type hints)
from .models import (
    Achievement,
    Friend,
    GlobalStat,
    InventoryItem,
    MarketListing,
    NewsItem,
    OwnedGame,
    PlayerBan,
    PlayerCount,
    PlayerSummary,
    PriceInfo,
    SteamApp,
    UserStat,
)

# API classes (for advanced users who want direct access)
from .repos import FamilyAPI, GameAPI, MarketAPI, PlayerAPI, StatsAPI
from .steam import Steam

__version__ = "1.0.0"

__all__ = [
    # Main client
    "Steam",
    # Core components
    "Client",
    "Settings",
    # Exceptions
    "SteamAPIError",
    "AuthenticationError",
    "RateLimitError",
    "PlayerNotFoundError",
    "GameNotFoundError",
    "InvalidSteamIDError",
    "InvalidAppIDError",
    "PrivateProfileError",
    "ServiceUnavailableError",
    "ConfigurationError",
    "ResponseParsingError",
    "NetworkError",
    # Common models
    "PlayerSummary",
    "Friend",
    "PlayerBan",
    "OwnedGame",
    "SteamApp",
    "Achievement",
    "PriceInfo",
    "MarketListing",
    "InventoryItem",
    "GlobalStat",
    "UserStat",
    "PlayerCount",
    "NewsItem",
    # API classes
    "PlayerAPI",
    "GameAPI",
    "MarketAPI",
    "StatsAPI",
    "FamilyAPI",
    # Version
    "__version__",
]
