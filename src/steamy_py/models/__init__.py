"""Data models for Steam API."""

# Base models
from .base import ErrorResponse, PaginatedResponse, SteamModel, SteamResponse

# Game models
from .game import (
    Achievement,
    AppDetails,
    AppListResponse,
    GameSchema,
    GameSchemaResponse,
    GameStat,
    GetAppListResponse,
    GetOwnedGamesResponse,
    GetPlayerAchievementsResponse,
    GetSchemaResponse,
    GetUserStatsResponse,
    OwnedGame,
    OwnedGamesResponse,
    PlayerAchievementsResponse,
    SchemaAchievement,
    SchemaStat,
    SteamApp,
    UserStatsResponse,
)

# Market models
from .market import (
    InventoryItem,
    InventoryResponse,
    ItemDescription,
    ItemPriceResponse,
    MarketHistoryEntry,
    MarketHistoryResponse,
    MarketItem,
    MarketListing,
    MarketListingsResponse,
    MarketSearch,
    PriceInfo,
)

# Player models
from .player import (
    CommunityVisibilityState,
    Friend,
    FriendsListResponse,
    PersonaState,
    PlayerBan,
    PlayerBansResponse,
    PlayerSummariesResponse,
    PlayerSummary,
    ResolveVanityURLResponse,
    VanityURLResolution,
)

# Stats models
from .stats import (
    GetGlobalAchievementResponse,
    GetGlobalStatsResponse,
    GetNewsResponse,
    GetPlayerCountResponse,
    GetUserStatsGameResponse,
    GlobalAchievementResponse,
    GlobalAchievementStat,
    GlobalStat,
    GlobalStatsResponse,
    LeaderboardEntry,
    LeaderboardResponse,
    NewsItem,
    NewsResponse,
    PlayerCount,
    PlayerCountResponse,
    UserAchievement,
    UserStat,
)
from .stats import (
    UserStatsResponse as StatsUserStatsResponse,
)

__all__ = [
    # Base models
    "SteamModel",
    "SteamResponse",
    "PaginatedResponse",
    "ErrorResponse",
    # Player models
    "PersonaState",
    "CommunityVisibilityState",
    "PlayerSummary",
    "Friend",
    "PlayerBan",
    "VanityURLResolution",
    "PlayerSummariesResponse",
    "FriendsListResponse",
    "PlayerBansResponse",
    "ResolveVanityURLResponse",
    # Game models
    "OwnedGame",
    "SteamApp",
    "Achievement",
    "GameStat",
    "GameSchema",
    "SchemaAchievement",
    "SchemaStat",
    "AppDetails",
    "OwnedGamesResponse",
    "AppListResponse",
    "PlayerAchievementsResponse",
    "UserStatsResponse",
    "GameSchemaResponse",
    "GetOwnedGamesResponse",
    "GetAppListResponse",
    "GetPlayerAchievementsResponse",
    "GetUserStatsResponse",
    "GetSchemaResponse",
    # Market models
    "MarketItem",
    "PriceInfo",
    "MarketListing",
    "MarketHistoryEntry",
    "MarketSearch",
    "InventoryItem",
    "ItemDescription",
    "ItemPriceResponse",
    "MarketListingsResponse",
    "MarketHistoryResponse",
    "InventoryResponse",
    # Stats models
    "GlobalStat",
    "UserStat",
    "UserAchievement",
    "GlobalAchievementStat",
    "PlayerCount",
    "NewsItem",
    "LeaderboardEntry",
    "GlobalStatsResponse",
    "StatsUserStatsResponse",
    "GlobalAchievementResponse",
    "PlayerCountResponse",
    "NewsResponse",
    "LeaderboardResponse",
    "GetGlobalStatsResponse",
    "GetUserStatsGameResponse",
    "GetGlobalAchievementResponse",
    "GetPlayerCountResponse",
    "GetNewsResponse",
]
