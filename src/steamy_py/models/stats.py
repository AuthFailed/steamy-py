"""Statistics related data models for Steam API."""

from datetime import datetime
from typing import Any, Union

from pydantic import Field

from .base import SteamModel, SteamResponse


class GlobalStat(SteamModel):
    """Global game statistic."""

    name: str = Field(description="Statistic name")
    total: Union[int, float] = Field(description="Total value across all players")


class UserStat(SteamModel):
    """User statistic for a game."""

    name: str = Field(description="Statistic name")
    value: Union[int, float] = Field(description="Statistic value")


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

    player_count: int = Field(description="Current number of players")
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


class LeaderboardEntry(SteamModel):
    """Leaderboard entry."""

    steamid: str = Field(description="Player Steam ID")
    rank: int = Field(description="Player rank")
    score: int = Field(description="Player score")
    details: bytes | None = Field(default=None, description="Additional details")

    # Additional player info (if requested)
    persona_name: str | None = Field(default=None, description="Player display name")
    avatar: str | None = Field(default=None, description="Player avatar URL")


# Response wrapper models
class GlobalStatsResponse(SteamModel):
    """Response wrapper for GetGlobalStatsForGame."""

    result: int = Field(description="Result code")
    globalstats: dict[str, Union[int, float]] = Field(
        description="Global statistics data"
    )

    @property
    def is_success(self) -> bool:
        """Check if request was successful."""
        return self.result == 1

    def to_global_stats(self) -> list[GlobalStat]:
        """Convert to list of GlobalStat objects."""
        return [
            GlobalStat(name=name, total=value)
            for name, value in self.globalstats.items()
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

    achievementpercentages: dict[str, Any] = Field(
        description="Achievement percentages"
    )

    def to_achievement_stats(self) -> list[GlobalAchievementStat]:
        """Convert to list of GlobalAchievementStat objects."""
        achievements = self.achievementpercentages.get("achievements", [])
        return [
            GlobalAchievementStat(name=ach["name"], percent=ach["percent"])
            for ach in achievements
        ]


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


class LeaderboardResponse(SteamModel):
    """Response wrapper for leaderboard data."""

    resultCount: int = Field(description="Number of results")
    totalLeaderboardEntryCount: int = Field(description="Total entries in leaderboard")
    leaderboardEntries: list[LeaderboardEntry] = Field(
        description="Leaderboard entries"
    )

    @property
    def has_more_entries(self) -> bool:
        """Check if there are more entries available."""
        return self.resultCount < self.totalLeaderboardEntryCount


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
