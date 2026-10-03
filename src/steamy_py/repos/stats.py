"""Stats endpoints (steam.stats): achievements, stats, schemas and player counts."""

import logging
from collections.abc import Iterable
from typing import Any

from ..exceptions import (
    GameNotFoundError,
    ResponseParsingError,
    SteamAPIError,
)
from ..models.game import (
    Achievement,
    GameSchema,
    GetPlayerAchievementsResponse,
    GetSchemaResponse,
)
from ..models.stats import (
    AchievementProgress,
    AchievementsProgressResponse,
    GameAchievements,
    GameAchievementsResponse,
    GetGlobalAchievementResponse,
    GetGlobalStatsResponse,
    GetPlayerCountResponse,
    GetUserStatsGameResponse,
    GlobalAchievementStat,
    GlobalStat,
    NewsItem,
    PlayerCount,
    TopAchievementsForGamesResponse,
    TopAchievementsGame,
    UserAchievement,
    UserStat,
    UserStatsResponse,
)
from ..steamid import SteamIDLike, validate_app_id, validate_steam_id
from .base import BaseAPI

logger = logging.getLogger(__name__)

_PLAYER_SERVICE = "IPlayerService"


def _app_ids(appids: Any) -> list[int]:
    """Validate one App ID or several; a str or bytes counts as one (invalid)
    id."""
    if isinstance(appids, str | bytes | bytearray) or not isinstance(appids, Iterable):
        appids = [appids]
    ids = [validate_app_id(appid) for appid in appids]
    if not ids:
        raise ValueError("At least one App ID must be provided")
    return ids


class StatsAPI(BaseAPI):
    """Achievements and stats: per player, global, schemas and player counts."""

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
        validate_app_id(app_id)

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

        with self._errors("get global stats"):
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetGlobalStatsForGame",
                version="v1",
                auth_type="none",
                params=params,
            )

            if "response" not in response_data:
                raise GameNotFoundError(
                    str(app_id), "Game not found or has no statistics"
                )

            response_obj = GetGlobalStatsResponse.model_validate(response_data)

            if not response_obj.response.is_success:
                raise GameNotFoundError(str(app_id), "Game statistics not available")

            return response_obj.response.to_global_stats()

    async def get_user_stats_for_game(
        self, steamid: SteamIDLike, app_id: int
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
        steamid = validate_steam_id(steamid)
        validate_app_id(app_id)

        with self._errors("get user stats"):
            try:
                response_data = await self._request(
                    interface="ISteamUserStats",
                    method="GetUserStatsForGame",
                    version="v2",
                    params={"steamid": steamid, "appid": str(app_id)},
                )
            except SteamAPIError as e:
                response_data = self._playerstats_body(e)

            if "playerstats" not in response_data:
                raise GameNotFoundError(
                    str(app_id), "Game not found or player has no stats"
                )

            playerstats = response_data["playerstats"]
            if "error" in playerstats:
                self._raise_playerstats_error(
                    str(playerstats["error"]), steamid, app_id
                )

            response_obj = GetUserStatsGameResponse.model_validate(response_data)
            return response_obj.playerstats

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
        validate_app_id(app_id)

        with self._errors("get achievement percentages"):
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetGlobalAchievementPercentagesForApp",
                version="v2",
                auth_type="none",
                params={"gameid": str(app_id)},
            )

            if "achievementpercentages" not in response_data:
                raise GameNotFoundError(
                    str(app_id), "Game not found or has no achievements"
                )

            response_obj = GetGlobalAchievementResponse.model_validate(response_data)
            return response_obj.achievementpercentages.to_achievement_stats()

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
        validate_app_id(app_id)

        with self._errors("get current players"):
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetNumberOfCurrentPlayers",
                version="v1",
                auth_type="none",
                params={"appid": str(app_id)},
            )

            if "response" not in response_data:
                raise GameNotFoundError(str(app_id), "Game not found")

            response_obj = GetPlayerCountResponse.model_validate(response_data)

            if not response_obj.response.is_success:
                raise GameNotFoundError(
                    str(app_id), "Unable to get player count for this game"
                )

            return response_obj.response

    async def get_player_achievements(
        self, steamid: SteamIDLike, app_id: int, language: str = "english"
    ) -> list[Achievement]:
        """Get player achievements for a specific game.

        Args:
            steamid: Steam ID of the player
            app_id: Steam App ID of the game
            language: Language for achievement names

        Returns:
            List of achievements

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            InvalidAppIDError: If App ID is invalid
            GameNotFoundError: If game not found
            PrivateProfileError: If profile is private
            SteamAPIError: On API errors
        """
        steamid = validate_steam_id(steamid)
        validate_app_id(app_id)

        with self._errors("get player achievements"):
            try:
                response_data = await self._request(
                    interface="ISteamUserStats",
                    method="GetPlayerAchievements",
                    version="v1",
                    params={"steamid": steamid, "appid": str(app_id), "l": language},
                )
            except SteamAPIError as e:
                response_data = self._playerstats_body(e)

            if "playerstats" not in response_data:
                raise ResponseParsingError("Invalid response structure from Steam API")

            playerstats = response_data["playerstats"]

            if not playerstats.get("success", False):
                self._raise_playerstats_error(
                    str(playerstats.get("error", "Unknown error")), steamid, app_id
                )

            response_obj = GetPlayerAchievementsResponse.model_validate(response_data)
            return response_obj.playerstats.achievements

    async def get_schema_for_game(
        self, app_id: int, language: str = "english"
    ) -> GameSchema:
        """Get achievements and stats schema for a game.

        Args:
            app_id: Steam App ID of the game
            language: Language for schema information

        Returns:
            Game schema information

        Raises:
            InvalidAppIDError: If App ID is invalid
            GameNotFoundError: If game not found
            SteamAPIError: On API errors
        """
        validate_app_id(app_id)

        with self._errors("get game schema"):
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetSchemaForGame",
                version="v2",
                params={"appid": str(app_id), "l": language},
            )

            if not response_data.get("game"):
                # No such app, or an app without stats: Steam sends {"game": {}}
                raise GameNotFoundError(
                    str(app_id), "Game not found or has no statistics"
                )

            response_obj = GetSchemaResponse.model_validate(response_data)
            return response_obj.game

    async def get_user_achievements_only(
        self, steamid: SteamIDLike, app_id: int
    ) -> list[UserAchievement]:
        """Get a user's achievements for a game, locked and unlocked.

        Uses ``GetPlayerAchievements``, which lists every achievement with
        its unlock time (``GetUserStatsForGame`` lists only unlocked ones).

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
        achievements = await self.get_player_achievements(steamid, app_id)
        return [
            UserAchievement(
                name=achievement.apiname,
                achieved=achievement.achieved,
                unlocktime=achievement.unlocktime,
            )
            for achievement in achievements
        ]

    async def get_user_stats_only(
        self, steamid: SteamIDLike, app_id: int
    ) -> list[UserStat]:
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

    async def get_news_for_app(
        self,
        app_id: int,
        count: int = 20,
        max_length: int = 300,
        end_date: int | None = None,
        feeds: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[NewsItem]:
        """Deprecated: use ``Steam.store.get_news_for_app``."""
        from .store import StoreAPI

        self._deprecated("StatsAPI.get_news_for_app", "Steam.store.get_news_for_app")
        return await StoreAPI(self.client).get_news_for_app(
            app_id, count, max_length, end_date, feeds, tags
        )

    async def get_achievements_progress(
        self,
        steamid: SteamIDLike,
        appids: int | Iterable[int],
        language: str = "english",
        *,
        include_unvetted_apps: bool | None = None,
    ) -> list[AchievementProgress]:
        """Get how many achievements a user has unlocked in each of some apps.

        Calls IPlayerService/GetAchievementsProgress as a POST (Steam lists
        it as POST-only), with the API key if the client has one, else the
        access token; inputs and credential go in the form body. Steam does
        not document which credential it accepts: browser extensions call it
        with the signed-in user's access token, and Steam's method metadata
        (SteamDatabase/Protobufs) gives it the same requirements as
        GetOwnedGames, which takes either. How Steam answers for a private
        profile is unverified.

        Args:
            steamid: Steam ID of the user (int, str or SteamID)
            appids: One App ID or several
            language: Steam language name (e.g. "english")
            include_unvetted_apps: Steam's ``include_unvetted_apps`` flag;
                left out when None (its effect is unverified)

        Returns:
            One entry per app Steam reports on (unlocked, total, percentage)

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            InvalidAppIDError: If an App ID is invalid
            ValueError: If no App ID is given
            AuthenticationError: If the client has neither an API key nor an
                access token, or Steam rejects it
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        inputs = {
            "steamid": validate_steam_id(steamid),
            "language": language,
            "appids": _app_ids(appids),
            "include_unvetted_apps": include_unvetted_apps,
        }
        result = await self._call_service(
            _PLAYER_SERVICE,
            "GetAchievementsProgress",
            "get achievements progress",
            inputs,
            model=AchievementsProgressResponse,
            http_method="POST",
            auth_type="any",
        )
        return result.response.achievement_progress

    async def get_game_achievements(
        self, appid: int, language: str = "english"
    ) -> GameAchievements:
        """Get an app's achievements for display, with global unlock rates.

        Calls IPlayerService/GetGameAchievements without a credential: Steam's
        method metadata marks it like other keyless methods (GetWishlist,
        GetMostPlayedGames), and published clients call it without one. An
        app without achievements comes back with an empty ``achievements``
        list (unverified).

        Args:
            appid: Steam App ID
            language: Steam language name for names and descriptions
                (e.g. "english", "german")

        Returns:
            The achievements (API name, display name, description, icon file
            names, hidden flag, unlock percentage) and their groups

        Raises:
            InvalidAppIDError: If the App ID is invalid
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        result = await self._call_service(
            _PLAYER_SERVICE,
            "GetGameAchievements",
            "get game achievements",
            {"appid": validate_app_id(appid), "language": language},
            model=GameAchievementsResponse,
            auth_type="none",
        )
        return result.response

    async def get_top_achievements_for_games(
        self,
        steamid: SteamIDLike,
        appids: int | Iterable[int],
        language: str = "english",
        max_achievements: int | None = None,
    ) -> list[TopAchievementsGame]:
        """Get a user's "best" unlocked achievements in each of some apps.

        Calls IPlayerService/GetTopAchievementsForGames with the API key if
        the client has one, else the access token (Steam's method metadata
        allows either; unverified with an access token).

        Args:
            steamid: Steam ID of the user (int, str or SteamID)
            appids: One App ID or several
            language: Steam language name for names and descriptions
            max_achievements: Achievements to return per app; Steam's API
                list documents a maximum of 8. Left out when None, and how many
                Steam then returns is unverified.

        Returns:
            One entry per app with its achievement count and the chosen
            achievements

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            InvalidAppIDError: If an App ID is invalid
            ValueError: If no App ID is given, or ``max_achievements`` is not a
                positive int
            AuthenticationError: If the client has neither an API key nor an
                access token, or Steam rejects it
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        if max_achievements is not None and (
            isinstance(max_achievements, bool)
            or not isinstance(max_achievements, int)
            or max_achievements < 1
        ):
            raise ValueError(
                f"max_achievements must be a positive int, not {max_achievements!r}"
            )
        inputs = {
            "steamid": validate_steam_id(steamid),
            "language": language,
            "max_achievements": max_achievements,
            "appids": _app_ids(appids),
        }
        result = await self._call_service(
            _PLAYER_SERVICE,
            "GetTopAchievementsForGames",
            "get top achievements for games",
            inputs,
            model=TopAchievementsForGamesResponse,
            auth_type="any",
        )
        return result.response.games
