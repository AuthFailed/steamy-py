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
from .repos import (
    AuthAPI,
    EconomyAPI,
    FamilyAPI,
    FriendsAPI,
    GameAPI,
    LibraryAPI,
    MarketAPI,
    NotificationsAPI,
    PlayerAPI,
    ServersAPI,
    StatsAPI,
    StoreAPI,
    UsersAPI,
    UtilAPI,
    WishlistAPI,
    WorkshopAPI,
)
from .steam import Steam
from .steamid import SteamID

__all__ = [
    "Achievement",
    "AuthAPI",
    "AuthenticationError",
    "Client",
    "ConfigurationError",
    "EconomyAPI",
    "FamilyAPI",
    "Friend",
    "FriendsAPI",
    "GameAPI",
    "GameNotFoundError",
    "GlobalStat",
    "InvalidAppIDError",
    "InvalidSteamIDError",
    "InventoryItem",
    "LibraryAPI",
    "MarketAPI",
    "MarketListing",
    "NetworkError",
    "NewsItem",
    "NotificationsAPI",
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
    "ServersAPI",
    "ServiceUnavailableError",
    "Settings",
    "StatsAPI",
    "Steam",
    "SteamAPIError",
    "SteamApp",
    "SteamID",
    "StoreAPI",
    "UserStat",
    "UsersAPI",
    "UtilAPI",
    "WishlistAPI",
    "WorkshopAPI",
    "__version__",
]

# A library leaves logging setup to the application (see #12).
logging.getLogger(__name__).addHandler(logging.NullHandler())
