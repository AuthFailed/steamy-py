"""Game/App related data models for Steam API."""

from datetime import datetime
from typing import Any

from pydantic import Field

from .base import SteamModel, SteamResponse


class OwnedGame(SteamModel):
    """Game owned by a Steam user."""

    appid: int = Field(description="Unique identifier for the game")
    name: str | None = Field(default=None, description="Game name")
    playtime_forever: int = Field(description="Total playtime in minutes")
    img_icon_url: str | None = Field(default=None, description="Icon image filename")
    img_logo_url: str | None = Field(default=None, description="Logo image filename")

    # Recent playtime data
    playtime_windows_forever: int | None = Field(
        default=None, description="Windows playtime in minutes"
    )
    playtime_mac_forever: int | None = Field(
        default=None, description="Mac playtime in minutes"
    )
    playtime_linux_forever: int | None = Field(
        default=None, description="Linux playtime in minutes"
    )
    playtime_2weeks: int | None = Field(
        default=None, description="Playtime in last 2 weeks (minutes)"
    )

    @property
    def playtime_hours(self) -> float:
        """Get total playtime in hours."""
        return round(self.playtime_forever / 60, 1)

    @property
    def playtime_2weeks_hours(self) -> float | None:
        """Get recent playtime in hours."""
        return round(self.playtime_2weeks / 60, 1) if self.playtime_2weeks else None

    @property
    def icon_url(self) -> str | None:
        """Get full icon URL."""
        if self.img_icon_url:
            return f"http://media.steampowered.com/steamcommunity/public/images/apps/{self.appid}/{self.img_icon_url}.jpg"
        return None

    @property
    def logo_url(self) -> str | None:
        """Get full logo URL."""
        if self.img_logo_url:
            return f"http://media.steampowered.com/steamcommunity/public/images/apps/{self.appid}/{self.img_logo_url}.jpg"
        return None


class SteamApp(SteamModel):
    """Steam application/game from the app list."""

    appid: int = Field(description="Unique identifier for the application")
    name: str = Field(description="Application name")


class Achievement(SteamModel):
    """Player achievement for a game."""

    apiname: str = Field(description="Achievement API name")
    achieved: int = Field(description="Achievement status (1=achieved, 0=not achieved)")
    unlocktime: int = Field(
        description="Unix timestamp when achieved (0 if not achieved)"
    )
    name: str | None = Field(default=None, description="Achievement display name")
    description: str | None = Field(default=None, description="Achievement description")

    @property
    def is_achieved(self) -> bool:
        """Check if achievement is unlocked."""
        return self.achieved == 1

    @property
    def unlock_date(self) -> datetime | None:
        """Get achievement unlock date."""
        if self.is_achieved and self.unlocktime > 0:
            return datetime.fromtimestamp(self.unlocktime)
        return None


class GameStat(SteamModel):
    """Player statistic for a game."""

    name: str = Field(description="Stat name")
    value: int = Field(description="Stat value")


class GameSchema(SteamModel):
    """Game statistics and achievements schema."""

    gameName: str = Field(description="Game name")
    gameVersion: str = Field(description="Game version")
    availableGameStats: dict[str, Any] | None = Field(
        default=None, description="Available game statistics"
    )


class SchemaAchievement(SteamModel):
    """Achievement definition from game schema."""

    name: str = Field(description="Achievement internal name")
    displayName: str = Field(description="Achievement display name")
    description: str = Field(description="Achievement description")
    icon: str = Field(description="Achievement icon URL")
    icongray: str = Field(description="Achievement icon URL (locked)")
    hidden: int | None = Field(default=0, description="Hidden achievement flag")

    @property
    def is_hidden(self) -> bool:
        """Check if achievement is hidden."""
        return self.hidden == 1


class SchemaStat(SteamModel):
    """Statistic definition from game schema."""

    name: str = Field(description="Stat internal name")
    displayName: str = Field(description="Stat display name")
    defaultvalue: int = Field(description="Default value")


# Response wrapper models
class OwnedGamesResponse(SteamModel):
    """Response wrapper for GetOwnedGames."""

    game_count: int = Field(description="Total number of games")
    games: list[OwnedGame] = Field(
        default_factory=list, description="List of owned games"
    )


class AppListResponse(SteamModel):
    """Response wrapper for GetAppList."""

    apps: list[SteamApp] = Field(description="List of Steam applications")


class PlayerAchievementsResponse(SteamModel):
    """Response wrapper for GetPlayerAchievements."""

    steamID: str = Field(description="Player Steam ID")
    gameName: str = Field(description="Game name")
    achievements: list[Achievement] = Field(
        default_factory=list, description="Player achievements"
    )
    success: bool = Field(description="Request success status")


class UserStatsResponse(SteamModel):
    """Response wrapper for GetUserStatsForGame."""

    steamID: str = Field(description="Player Steam ID")
    gameName: str = Field(description="Game name")
    stats: list[GameStat] = Field(default_factory=list, description="Player statistics")
    achievements: list[Achievement] = Field(
        default_factory=list, description="Player achievements"
    )


class GameSchemaResponse(SteamModel):
    """Response wrapper for GetSchemaForGame."""

    game: GameSchema = Field(description="Game schema information")


# Top-level response wrappers
class GetOwnedGamesResponse(SteamResponse):
    """Top-level response for GetOwnedGames."""

    response: OwnedGamesResponse = Field(description="Owned games data")


class GetAppListResponse(SteamResponse):
    """Top-level response for GetAppList."""

    applist: AppListResponse = Field(description="App list data")


class GetPlayerAchievementsResponse(SteamResponse):
    """Top-level response for GetPlayerAchievements."""

    playerstats: PlayerAchievementsResponse = Field(
        description="Player achievements data"
    )


class GetUserStatsResponse(SteamResponse):
    """Top-level response for GetUserStatsForGame."""

    playerstats: UserStatsResponse = Field(description="Player stats data")


class GetSchemaResponse(SteamResponse):
    """Top-level response for GetSchemaForGame."""

    game: GameSchema = Field(description="Game schema")


# App details from Store API
class AppDetails(SteamModel):
    """Steam Store app details."""

    type: str = Field(description="Application type")
    name: str = Field(description="Application name")
    steam_appid: int = Field(description="Steam App ID")
    required_age: int = Field(description="Required age")
    is_free: bool = Field(description="Free to play status")
    short_description: str = Field(description="Short description")
    header_image: str = Field(description="Header image URL")
    website: str | None = Field(default=None, description="Official website")
    developers: list[str] = Field(default_factory=list, description="Developer names")
    publishers: list[str] = Field(default_factory=list, description="Publisher names")
    price_overview: dict[str, Any] | None = Field(
        default=None, description="Pricing information"
    )
    platforms: dict[str, bool] = Field(description="Platform availability")
    categories: list[dict[str, Any]] = Field(
        default_factory=list, description="Game categories"
    )
    genres: list[dict[str, Any]] = Field(
        default_factory=list, description="Game genres"
    )
    release_date: dict[str, Any] = Field(description="Release date information")

    @property
    def is_released(self) -> bool:
        """Check if game is released."""
        return not self.release_date.get("coming_soon", True)

    @property
    def platform_list(self) -> list[str]:
        """Get list of supported platforms."""
        return [platform for platform, supported in self.platforms.items() if supported]
