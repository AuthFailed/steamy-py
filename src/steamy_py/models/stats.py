"""Statistics related data models for Steam API."""

from datetime import datetime
from enum import IntEnum
from typing import Any

from pydantic import Field

from .base import SteamModel, SteamResponse


class GlobalStat(SteamModel):
    """Global game statistic."""

    name: str = Field(description="Statistic name")
    total: int | float = Field(description="Total value across all players")


class UserStat(SteamModel):
    """User statistic for a game."""

    name: str = Field(description="Statistic name")
    value: int | float = Field(description="Statistic value")


class UserAchievement(SteamModel):
    """User achievement from stats API."""

    name: str = Field(description="Achievement internal name")
    achieved: int = Field(description="Achievement status (1=achieved, 0=not achieved)")
    unlocktime: int | None = Field(
        default=0, description="Unix timestamp when achieved"
    )

    @property
    def is_achieved(self) -> bool:
        """Check if achievement is unlocked."""
        return self.achieved == 1

    @property
    def unlock_date(self) -> datetime | None:
        """Get achievement unlock date."""
        if self.is_achieved and self.unlocktime and self.unlocktime > 0:
            return datetime.fromtimestamp(self.unlocktime)
        return None


class GlobalAchievementStat(SteamModel):
    """Global achievement statistics."""

    name: str = Field(description="Achievement internal name")
    percent: float = Field(
        description="Percentage of players who have this achievement"
    )

    @property
    def completion_rate(self) -> float:
        """Get completion rate as decimal (0.0 to 1.0)."""
        return self.percent / 100.0


class PlayerCount(SteamModel):
    """Current player count for a game."""

    player_count: int = Field(
        default=0,
        description="Current number of players (Steam omits it for unknown apps)",
    )
    result: int = Field(description="Result code (1=success)")

    @property
    def is_success(self) -> bool:
        """Check if request was successful."""
        return self.result == 1


class NewsItem(SteamModel):
    """Steam news item."""

    gid: str = Field(description="News item ID")
    title: str = Field(description="News title")
    url: str = Field(description="News URL")
    is_external_url: bool = Field(description="Whether URL is external")
    author: str = Field(description="Author name")
    contents: str = Field(description="News content")
    feedlabel: str = Field(description="Feed label")
    date: int = Field(description="Publication date (Unix timestamp)")
    feedname: str = Field(description="Feed name")
    feed_type: int = Field(description="Feed type")
    appid: int = Field(description="Associated App ID")

    @property
    def publish_date(self) -> datetime:
        """Get publication date as datetime."""
        return datetime.fromtimestamp(self.date)

    @property
    def is_official(self) -> bool:
        """Check if news is from official Steam feed."""
        return self.feed_type == 1


# Response wrapper models
class GlobalStatTotal(SteamModel):
    """One stat in a GetGlobalStatsForGame response.

    Steam sends the total as a string, e.g. ``{"total": "2346826"}``.
    """

    total: int | float = Field(description="Total value across all players")
    history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-day totals when a date range was requested",
    )


class GlobalStatsResponse(SteamModel):
    """Response wrapper for GetGlobalStatsForGame."""

    result: int = Field(description="Result code")
    globalstats: dict[str, GlobalStatTotal] = Field(
        default_factory=dict, description="Global statistics data"
    )

    @property
    def is_success(self) -> bool:
        """Check if request was successful."""
        return self.result == 1

    def to_global_stats(self) -> list[GlobalStat]:
        """Convert to list of GlobalStat objects."""
        return [
            GlobalStat(name=name, total=stat.total)
            for name, stat in self.globalstats.items()
        ]


class UserStatsResponse(SteamModel):
    """Response wrapper for GetUserStatsForGame."""

    steamID: str = Field(description="Player Steam ID")
    gameName: str = Field(description="Game name")
    stats: list[UserStat] = Field(default_factory=list, description="User statistics")
    achievements: list[UserAchievement] = Field(
        default_factory=list, description="User achievements"
    )


class GlobalAchievementResponse(SteamModel):
    """Response wrapper for global achievement percentages."""

    achievements: list[GlobalAchievementStat] = Field(
        default_factory=list, description="Achievement percentages"
    )

    def to_achievement_stats(self) -> list[GlobalAchievementStat]:
        """Return the achievement percentages."""
        return list(self.achievements)


class PlayerCountResponse(SteamModel):
    """Response wrapper for GetNumberOfCurrentPlayers."""

    response: PlayerCount = Field(description="Player count data")


class NewsResponse(SteamModel):
    """Response wrapper for GetNewsForApp."""

    appnews: dict[str, Any] = Field(description="News data")

    def to_news_items(self) -> list[NewsItem]:
        """Convert to list of NewsItem objects."""
        newsitems = self.appnews.get("newsitems", [])
        return [NewsItem(**item) for item in newsitems]


# Top-level response wrappers
class GetGlobalStatsResponse(SteamResponse):
    """Top-level response for GetGlobalStatsForGame."""

    response: GlobalStatsResponse = Field(description="Global stats data")


class GetUserStatsGameResponse(SteamResponse):
    """Top-level response for GetUserStatsForGame."""

    playerstats: UserStatsResponse = Field(description="User stats data")


class GetGlobalAchievementResponse(SteamResponse):
    """Top-level response for GetGlobalAchievementPercentagesForApp."""

    achievementpercentages: GlobalAchievementResponse = Field(
        description="Achievement percentage data"
    )


class GetPlayerCountResponse(SteamResponse):
    """Top-level response for GetNumberOfCurrentPlayers."""

    response: PlayerCount = Field(description="Player count data")


class GetNewsResponse(SteamResponse):
    """Top-level response for GetNewsForApp."""

    appnews: dict[str, Any] = Field(description="News data")

    def to_news_items(self) -> list[NewsItem]:
        """Convert to list of NewsItem objects."""
        newsitems = self.appnews.get("newsitems", [])
        return [NewsItem(**item) for item in newsitems]


# -- IPlayerService achievement summaries ------------------------------------
#
# IPlayerService serializes protobuf messages (CPlayer_GetAchievementsProgress_
# Response, CPlayer_GetGameAchievements_Response and
# CPlayer_GetTopAchievementsForGames_Response in SteamDatabase/Protobufs) and
# may leave out any field at its default value, so every field has a default.


def _percent(text: str) -> float | None:
    """``player_percent_unlocked`` (a string such as "26.8") as a float."""
    try:
        return float(text) if text else None
    except ValueError:
        return None


class EAchievementProgressType(IntEnum):
    """Kind of progress bar of an achievement (``progress_type``)."""

    INVALID = 0
    INT = 1
    FLOAT = 2


class AchievementProgress(SteamModel):
    """A user's achievement completion in one app."""

    appid: int = Field(default=0, description="App ID")
    unlocked: int = Field(default=0, description="Achievements the user unlocked")
    total: int = Field(default=0, description="Achievements the app has")
    percentage: float = Field(
        default=0.0, description="unlocked / total, in percent (0 to 100)"
    )
    all_unlocked: bool = Field(
        default=False, description="Whether every achievement is unlocked"
    )
    cache_time: int = Field(
        default=0,
        description="Unix timestamp; unverified: when Steam computed these counts",
    )
    vetted: bool = Field(
        default=False,
        description=(
            "Unverified: whether Steam counts the app towards the user's "
            "overall completion rate"
        ),
    )


class AchievementsProgress(SteamModel):
    """IPlayerService/GetAchievementsProgress response body."""

    achievement_progress: list[AchievementProgress] = Field(
        default_factory=list, description="One entry per app Steam reported on"
    )


class AchievementsProgressResponse(SteamModel):
    """Response wrapper for IPlayerService/GetAchievementsProgress."""

    response: AchievementsProgress = Field(default_factory=AchievementsProgress)


class GameAchievement(SteamModel):
    """An achievement of an app, for display."""

    internal_name: str = Field(
        default="", description="API name (``name`` in GetSchemaForGame)"
    )
    localized_name: str = Field(default="", description="Display name")
    localized_desc: str = Field(default="", description="Description")
    icon: str = Field(
        default="",
        description="File name of the icon, under images/apps/<appid>/ on "
        "Steam's community CDN",
    )
    icon_gray: str = Field(
        default="", description="File name of the locked (gray) icon"
    )
    hidden: bool = Field(
        default=False, description="Whether the achievement is hidden until unlocked"
    )
    player_percent_unlocked: str = Field(
        default="",
        description="Share of players who unlocked it, in percent, as the string "
        'Steam sends (e.g. "26.8"); see ``percent_unlocked``',
    )
    internal_key: int = 0
    min_progress_int: int = 0
    max_progress_int: int = 0
    groupid: int = Field(default=0, description="``groupid`` of its group, if any")
    archived: bool = False
    progress_type: int = Field(
        default=EAchievementProgressType.INVALID,
        description="Kind of progress bar (``EAchievementProgressType``)",
    )
    min_progress_float: float = 0.0
    max_progress_float: float = 0.0

    @property
    def percent_unlocked(self) -> float | None:
        """``player_percent_unlocked`` as a float; None when missing or not a
        number."""
        return _percent(self.player_percent_unlocked)


class GameAchievementGroup(SteamModel):
    """A group of achievements, e.g. those added by a DLC."""

    groupid: int = 0
    localized_name: str = ""
    dlcappid: int = Field(default=0, description="App ID of the DLC, if any")
    archived: bool = False
    developeronly: bool = False
    order: int = 0
    ispublic: bool = False
    total_achievements: int = 0
    completion_achievements: int = 0


class GameAchievements(SteamModel):
    """IPlayerService/GetGameAchievements response body."""

    achievements: list[GameAchievement] = Field(default_factory=list)
    schema_version: int = 0
    groups: list[GameAchievementGroup] = Field(default_factory=list)
    schema_hash: int = 0


class GameAchievementsResponse(SteamModel):
    """Response wrapper for IPlayerService/GetGameAchievements."""

    response: GameAchievements = Field(default_factory=GameAchievements)


class TopAchievement(SteamModel):
    """One of the rarest achievements a user unlocked in an app."""

    statid: int = Field(default=0, description="Stat that holds the achievement")
    bit: int = Field(default=0, description="Bit of the achievement in that stat")
    name: str = Field(default="", description="Display name")
    desc: str = Field(default="", description="Description")
    icon: str = Field(
        default="",
        description="File name of the icon, under images/apps/<appid>/ on "
        "Steam's community CDN",
    )
    icon_gray: str = Field(
        default="", description="File name of the locked (gray) icon"
    )
    hidden: bool = False
    player_percent_unlocked: str = Field(
        default="",
        description="Share of players who unlocked it, in percent, as the string "
        'Steam sends (e.g. "26.8"); see ``percent_unlocked``',
    )

    @property
    def percent_unlocked(self) -> float | None:
        """``player_percent_unlocked`` as a float; None when missing or not a
        number."""
        return _percent(self.player_percent_unlocked)


class TopAchievementsGame(SteamModel):
    """A user's top achievements in one app."""

    appid: int = Field(default=0, description="App ID")
    total_achievements: int = Field(
        default=0,
        description="Number of achievements of the app (unverified: the app's "
        "total, not the user's unlocked count)",
    )
    achievements: list[TopAchievement] = Field(
        default_factory=list,
        description='The user\'s "best" unlocked achievements, as Steam picks '
        "them (up to ``max_achievements``)",
    )


class TopAchievementsForGames(SteamModel):
    """IPlayerService/GetTopAchievementsForGames response body."""

    games: list[TopAchievementsGame] = Field(default_factory=list)


class TopAchievementsForGamesResponse(SteamModel):
    """Response wrapper for IPlayerService/GetTopAchievementsForGames."""

    response: TopAchievementsForGames = Field(default_factory=TopAchievementsForGames)
