import logging

# Core components (for advanced users)
from ._version import __version__
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

__all__ = [
    "Achievement",
    "AuthenticationError",
    "Client",
    "ConfigurationError",
    "FamilyAPI",
    "Friend",
    "GameAPI",
    "GameNotFoundError",
    "GlobalStat",
    "InvalidAppIDError",
    "InvalidSteamIDError",
    "InventoryItem",
    "MarketAPI",
    "MarketListing",
    "NetworkError",
    "NewsItem",
    "OwnedGame",
    "PlayerAPI",
    "PlayerBan",
    "PlayerCount",
    "PlayerNotFoundError",
    "PlayerSummary",
    "PriceInfo",
    "PrivateProfileError",
    "RateLimitError",
    "ResponseParsingError",
    "ServiceUnavailableError",
    "Settings",
    "StatsAPI",
    "Steam",
    "SteamAPIError",
    "SteamApp",
    "UserStat",
    "__version__",
]

# A library leaves logging setup to the application (see #12).
logging.getLogger(__name__).addHandler(logging.NullHandler())
