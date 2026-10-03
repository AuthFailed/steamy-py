"""Models for a user's game library: recently played games and playtimes.

IPlayerService leaves out every field Steam has no value for (or does not
share), so every field here has a default. Playtimes are in minutes and
times are Unix timestamps (0 when unknown).
"""

from pydantic import Field

from .base import SteamModel


class RecentlyPlayedGame(SteamModel):
    """A game played in the last two weeks (IPlayerService/GetRecentlyPlayedGames)."""

    appid: int = Field(default=0, description="App ID")
    name: str = Field(default="", description="Game name")
    playtime_2weeks: int = Field(
        default=0, description="Playtime in the last two weeks (minutes)"
    )
    playtime_forever: int = Field(default=0, description="Total playtime (minutes)")
    img_icon_url: str = Field(default="", description="Icon image hash")
    playtime_windows_forever: int = Field(
        default=0, description="Total playtime on Windows (minutes)"
    )
    playtime_mac_forever: int = Field(
        default=0, description="Total playtime on macOS (minutes)"
    )
    playtime_linux_forever: int = Field(
        default=0, description="Total playtime on Linux (minutes)"
    )
    playtime_deck_forever: int = Field(
        default=0, description="Total playtime on Steam Deck (minutes)"
    )

    @property
    def icon_url(self) -> str | None:
        """Full URL of the game's icon, or None without an icon hash."""
        if self.img_icon_url:
            return f"https://media.steampowered.com/steamcommunity/public/images/apps/{self.appid}/{self.img_icon_url}.jpg"
        return None


class RecentlyPlayedGames(SteamModel):
    """The games a user played in the last two weeks."""

    total_count: int = Field(
        default=0, description="Number of games played in the last two weeks"
    )
    games: list[RecentlyPlayedGame] = Field(
        default_factory=list, description="The games (at most ``count`` if given)"
    )


class RecentlyPlayedGamesResponse(SteamModel):
    """Response wrapper for IPlayerService/GetRecentlyPlayedGames."""

    response: RecentlyPlayedGames = Field(default_factory=RecentlyPlayedGames)


class LastPlayedGame(SteamModel):
    """Playtimes of one game (``CPlayer_GetLastPlayedTimes_Response.Game``)."""

    appid: int = Field(default=0, description="App ID")
    last_playtime: int = Field(default=0, description="Time last played")
    playtime_2weeks: int = Field(
        default=0, description="Playtime in the last two weeks (minutes)"
    )
    playtime_forever: int = Field(default=0, description="Total playtime (minutes)")
    first_playtime: int = Field(default=0, description="Time first played")
    playtime_windows_forever: int = Field(
        default=0, description="Total playtime on Windows (minutes)"
    )
    playtime_mac_forever: int = Field(
        default=0, description="Total playtime on macOS (minutes)"
    )
    playtime_linux_forever: int = Field(
        default=0, description="Total playtime on Linux (minutes)"
    )
    playtime_deck_forever: int = Field(
        default=0, description="Total playtime on Steam Deck (minutes)"
    )
    first_windows_playtime: int = Field(
        default=0, description="Time first played on Windows"
    )
    first_mac_playtime: int = Field(default=0, description="Time first played on macOS")
    first_linux_playtime: int = Field(
        default=0, description="Time first played on Linux"
    )
    first_deck_playtime: int = Field(
        default=0, description="Time first played on Steam Deck"
    )
    last_windows_playtime: int = Field(
        default=0, description="Time last played on Windows"
    )
    last_mac_playtime: int = Field(default=0, description="Time last played on macOS")
    last_linux_playtime: int = Field(default=0, description="Time last played on Linux")
    last_deck_playtime: int = Field(
        default=0, description="Time last played on Steam Deck"
    )
    playtime_disconnected: int = Field(
        default=0, description="Playtime while offline (minutes)"
    )


class LastPlayedTimes(SteamModel):
    """Body of ``CPlayer_GetLastPlayedTimes_Response``."""

    games: list[LastPlayedGame] = Field(default_factory=list)


class LastPlayedTimesResponse(SteamModel):
    """Response wrapper for IPlayerService/ClientGetLastPlayedTimes."""

    response: LastPlayedTimes = Field(default_factory=LastPlayedTimes)


class PrivateAppList(SteamModel):
    """The apps the signed-in user marked private (``CAccountPrivateAppList``)."""

    appids: list[int] = Field(default_factory=list, description="App IDs")


class PrivateApps(SteamModel):
    """Body of ``CAccountPrivateApps_GetPrivateAppList_Response``."""

    private_apps: PrivateAppList = Field(default_factory=PrivateAppList)


class PrivateAppsResponse(SteamModel):
    """Response wrapper for IAccountPrivateAppsService/GetPrivateAppList."""

    response: PrivateApps = Field(default_factory=PrivateApps)
