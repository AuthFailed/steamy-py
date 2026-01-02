"""Statistics API endpoints for Steam API."""

import logging

from ..exceptions import (
    GameNotFoundError,
    InvalidAppIDError,
    InvalidSteamIDError,
    PrivateProfileError,
    SteamAPIError,
)
from ..models.stats import (
    GetGlobalAchievementResponse,
    GetGlobalStatsResponse,
    GetNewsResponse,
    GetPlayerCountResponse,
    GetUserStatsGameResponse,
    GlobalAchievementStat,
    GlobalStat,
    NewsItem,
    PlayerCount,
    UserAchievement,
    UserStat,
    UserStatsResponse,
)
from .base import BaseAPI

logger = logging.getLogger(__name__)


class StatsAPI(BaseAPI):
    """Steam Statistics API endpoints."""

    async def get_global_stats_for_game(
        self,
        app_id: int,
        stat_names: list[str],
        start_date: int | None = None,
        end_date: int | None = None,
    ) -> list[GlobalStat]:
        """Get global statistics for a game.

        Args:
            app_id: Steam App ID
            stat_names: List of statistic names to retrieve
            start_date: Start date (Unix timestamp)
            end_date: End date (Unix timestamp)

        Returns:
            List of global statistics

        Raises:
            InvalidAppIDError: If App ID is invalid
            GameNotFoundError: If game not found or has no stats
            SteamAPIError: On API errors
        """
        self._validate_app_id(app_id)

        if not stat_names:
            raise ValueError("At least one stat name must be provided")

        params = {"appid": str(app_id), "count": str(len(stat_names))}

        # Add stat names
        for i, stat_name in enumerate(stat_names):
            params[f"name[{i}]"] = stat_name

        # Add date range if provided
        if start_date:
            params["startdate"] = str(start_date)
        if end_date:
            params["enddate"] = str(end_date)

        try:
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetGlobalStatsForGame",
                version="v1",
                params=params,
            )

            if "response" not in response_data:
                raise GameNotFoundError(
                    str(app_id), "Game not found or has no statistics"
                )

            response_obj = GetGlobalStatsResponse(**response_data)

            if not response_obj.response.is_success:
                raise GameNotFoundError(str(app_id), "Game statistics not available")

            return response_obj.response.to_global_stats()

        except GameNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting global stats for app {app_id}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get global stats: {e}")

    async def get_user_stats_for_game(
        self, steamid: str, app_id: int
    ) -> UserStatsResponse:
        """Get user statistics for a specific game.

        Args:
            steamid: Steam ID of the player
            app_id: Steam App ID

        Returns:
            User statistics and achievements

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            InvalidAppIDError: If App ID is invalid
            PrivateProfileError: If profile is private
            GameNotFoundError: If game not found
            SteamAPIError: On API errors
        """
        self._validate_steam_id(steamid)
        self._validate_app_id(app_id)

        try:
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetUserStatsForGame",
                version="v2",
                params={"steamid": steamid, "appid": str(app_id)},
            )

            if "playerstats" not in response_data:
                raise GameNotFoundError(
                    str(app_id), "Game not found or player has no stats"
                )

            playerstats = response_data["playerstats"]

            # Check for errors in the response
            if "error" in playerstats:
                error_msg = playerstats["error"]
                if "private" in error_msg.lower():
                    raise PrivateProfileError(steamid)
                elif "not found" in error_msg.lower():
                    raise GameNotFoundError(str(app_id))
                else:
                    raise SteamAPIError(f"Steam API error: {error_msg}")

            response_obj = GetUserStatsGameResponse(**response_data)
            return response_obj.playerstats

        except (PrivateProfileError, GameNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Error getting user stats for {steamid}, app {app_id}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get user stats: {e}")

    async def get_global_achievement_percentages(
        self, app_id: int
    ) -> list[GlobalAchievementStat]:
        """Get global achievement completion percentages for a game.

        Args:
            app_id: Steam App ID

        Returns:
            List of achievement completion statistics

        Raises:
            InvalidAppIDError: If App ID is invalid
            GameNotFoundError: If game not found or has no achievements
            SteamAPIError: On API errors
        """
        self._validate_app_id(app_id)

        try:
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetGlobalAchievementPercentagesForApp",
                version="v2",
                params={"gameid": str(app_id)},
            )

            if "achievementpercentages" not in response_data:
                raise GameNotFoundError(
                    str(app_id), "Game not found or has no achievements"
                )

            response_obj = GetGlobalAchievementResponse(**response_data)
            return response_obj.achievementpercentages.to_achievement_stats()

        except GameNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting achievement percentages for app {app_id}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get achievement percentages: {e}")

    async def get_current_players(self, app_id: int) -> PlayerCount:
        """Get current number of players for a game.

        Args:
            app_id: Steam App ID

        Returns:
            Current player count information

        Raises:
            InvalidAppIDError: If App ID is invalid
            GameNotFoundError: If game not found
            SteamAPIError: On API errors
        """
        self._validate_app_id(app_id)

        try:
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetNumberOfCurrentPlayers",
                version="v1",
                params={"appid": str(app_id)},
            )

            if "response" not in response_data:
                raise GameNotFoundError(str(app_id), "Game not found")

            response_obj = GetPlayerCountResponse(**response_data)

            if not response_obj.response.is_success:
                raise GameNotFoundError(
                    str(app_id), "Unable to get player count for this game"
                )

            return response_obj.response

        except GameNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting current players for app {app_id}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get current players: {e}")

    async def get_news_for_app(
        self, app_id: int, count: int = 20, max_length: int = 300
    ) -> list[NewsItem]:
        """Get news items for a game.

        Args:
            app_id: Steam App ID
            count: Number of news items to return (max 20)
            max_length: Maximum length of news content

        Returns:
            List of news items

        Raises:
            InvalidAppIDError: If App ID is invalid
            SteamAPIError: On API errors
        """
        self._validate_app_id(app_id)

        if count > 20:
            count = 20

        try:
            response_data = await self._request(
                interface="ISteamNews",
                method="GetNewsForApp",
                version="v2",
                params={
                    "appid": str(app_id),
                    "count": str(count),
                    "maxlength": str(max_length),
                },
            )

            if "appnews" not in response_data:
                return []

            response_obj = GetNewsResponse(**response_data)
            return response_obj.to_news_items()

        except Exception as e:
            logger.error(f"Error getting news for app {app_id}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get news: {e}")

    async def get_user_achievements_only(
        self, steamid: str, app_id: int
    ) -> list[UserAchievement]:
        """Get only user achievements (convenience method).

        Args:
            steamid: Steam ID of the player
            app_id: Steam App ID

        Returns:
            List of user achievements

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            InvalidAppIDError: If App ID is invalid
            PrivateProfileError: If profile is private
            GameNotFoundError: If game not found
            SteamAPIError: On API errors
        """
        user_stats = await self.get_user_stats_for_game(steamid, app_id)
        return user_stats.achievements

    async def get_user_stats_only(self, steamid: str, app_id: int) -> list[UserStat]:
        """Get only user statistics (convenience method).

        Args:
            steamid: Steam ID of the player
            app_id: Steam App ID

        Returns:
            List of user statistics

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            InvalidAppIDError: If App ID is invalid
            PrivateProfileError: If profile is private
            GameNotFoundError: If game not found
            SteamAPIError: On API errors
        """
        user_stats = await self.get_user_stats_for_game(steamid, app_id)
        return user_stats.stats

    def _validate_steam_id(self, steamid: str) -> None:
        """Validate Steam ID format.

        Args:
            steamid: Steam ID to validate

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
        """
        if not steamid:
            raise InvalidSteamIDError(steamid, "Steam ID cannot be empty")

        if not steamid.isdigit():
            raise InvalidSteamIDError(steamid, "Steam ID must be numeric")

        if len(steamid) != 17:
            raise InvalidSteamIDError(steamid, "Steam ID must be 17 digits long")

        if not steamid.startswith("7656119"):
            raise InvalidSteamIDError(steamid, "Invalid Steam ID format")

    def _validate_app_id(self, app_id: int) -> None:
        """Validate App ID format.

        Args:
            app_id: App ID to validate

        Raises:
            InvalidAppIDError: If App ID is invalid
        """
        if not isinstance(app_id, int) or app_id <= 0:
            raise InvalidAppIDError(str(app_id), "App ID must be a positive integer")
