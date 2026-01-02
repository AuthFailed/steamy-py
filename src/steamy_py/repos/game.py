"""Games/Apps API endpoints for Steam API."""

import logging

from ..exceptions import (
    GameNotFoundError,
    InvalidAppIDError,
    InvalidSteamIDError,
    PrivateProfileError,
    SteamAPIError,
)
from ..models.game import (
    Achievement,
    AppDetails,
    GameSchema,
    GetAppListResponse,
    GetOwnedGamesResponse,
    GetPlayerAchievementsResponse,
    GetSchemaResponse,
    OwnedGame,
    SteamApp,
)
from .base import BaseAPI

logger = logging.getLogger(__name__)


class GameAPI(BaseAPI):
    """Steam Games/Apps API endpoints."""

    async def get_owned_games(
        self,
        steamid: str,
        include_appinfo: bool = True,
        include_played_free_games: bool = False,
        appids_filter: list[int] | None = None,
    ) -> list[OwnedGame]:
        """Get games owned by a Steam user.

        Args:
            steamid: Steam ID of the user
            include_appinfo: Include game name and logo information
            include_played_free_games: Include free games that have been played
            appids_filter: Optional list of App IDs to filter results

        Returns:
            List of owned games

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            PrivateProfileError: If profile is private
            PlayerNotFoundError: If player not found
            SteamAPIError: On API errors
        """
        self._validate_steam_id(steamid)

        params = {
            "steamid": steamid,
            "include_appinfo": "1" if include_appinfo else "0",
            "include_played_free_games": "1" if include_played_free_games else "0",
        }

        if appids_filter:
            params["appids_filter"] = ",".join(map(str, appids_filter))

        try:
            response_data = await self._request(
                interface="IPlayerService",
                method="GetOwnedGames",
                version="v1",
                params=params,
            )

            if "response" not in response_data:
                raise SteamAPIError("Invalid response structure from Steam API")

            if not response_data["response"]:
                # Empty response usually means private profile
                raise PrivateProfileError(steamid)

            response_obj = GetOwnedGamesResponse(**response_data)
            return response_obj.response.games

        except PrivateProfileError:
            raise
        except Exception as e:
            logger.error(f"Error getting owned games for {steamid}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get owned games: {e}") from e

    async def get_app_list(self) -> list[SteamApp]:
        """Get list of all Steam applications.

        Returns:
            List of Steam applications

        Raises:
            SteamAPIError: On API errors
        """
        try:
            response_data = await self._request(
                interface="ISteamApps", method="GetAppList", version="v2"
            )

            if "applist" not in response_data:
                raise SteamAPIError("Invalid response structure from Steam API")

            response_obj = GetAppListResponse(**response_data)
            return response_obj.applist.apps

        except Exception as e:
            logger.error(f"Error getting app list: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get app list: {e}") from e

    async def get_player_achievements(
        self, steamid: str, app_id: int, language: str = "english"
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
        self._validate_steam_id(steamid)
        self._validate_app_id(app_id)

        try:
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetPlayerAchievements",
                version="v1",
                params={"steamid": steamid, "appid": str(app_id), "l": language},
            )

            if "playerstats" not in response_data:
                raise SteamAPIError("Invalid response structure from Steam API")

            playerstats = response_data["playerstats"]

            # Check if the request was successful
            if not playerstats.get("success", False):
                error = playerstats.get("error", "Unknown error")
                if "profile is private" in error.lower():
                    raise PrivateProfileError(steamid)
                elif "invalid appid" in error.lower() or "not found" in error.lower():
                    raise GameNotFoundError(str(app_id))
                else:
                    raise SteamAPIError(f"Steam API error: {error}")

            response_obj = GetPlayerAchievementsResponse(**response_data)
            return response_obj.playerstats.achievements

        except (PrivateProfileError, GameNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Error getting achievements for {steamid}, app {app_id}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get player achievements: {e}") from e

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
        self._validate_app_id(app_id)

        try:
            response_data = await self._request(
                interface="ISteamUserStats",
                method="GetSchemaForGame",
                version="v2",
                params={"appid": str(app_id), "l": language},
            )

            if "game" not in response_data:
                # This usually means the game doesn't exist or doesn't have stats
                raise GameNotFoundError(
                    str(app_id), "Game not found or has no statistics"
                )

            response_obj = GetSchemaResponse(**response_data)
            return response_obj.game

        except GameNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error getting schema for app {app_id}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get game schema: {e}") from e

    async def get_app_details(
        self, app_id: int, country: str = "US", language: str = "english"
    ) -> AppDetails | None:
        """Get detailed application information from Steam Store.

        Args:
            app_id: Steam App ID
            country: Country code for pricing
            language: Language for descriptions

        Returns:
            App details or None if not found

        Raises:
            InvalidAppIDError: If App ID is invalid
            SteamAPIError: On API errors
        """
        self._validate_app_id(app_id)

        try:
            response_data = await self._request_store(
                endpoint="appdetails",
                params={"appids": str(app_id), "cc": country, "l": language},
            )

            app_data = response_data.get(str(app_id))
            if not app_data or not app_data.get("success"):
                return None

            return AppDetails(**app_data["data"])

        except Exception as e:
            logger.error(f"Error getting app details for {app_id}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get app details: {e}") from e

    async def search_games(
        self, search_term: str, owned_games: list[OwnedGame] | None = None
    ) -> list[SteamApp]:
        """Search for games by name.

        Args:
            search_term: Search term
            owned_games: Optional list to search within (faster than full app list)

        Returns:
            List of matching games

        Note:
            This method searches locally through the app list. For more advanced
            search features, use the Steam Store web search.
        """
        search_term = search_term.lower().strip()

        if owned_games:
            # Search within owned games
            results = []
            for game in owned_games:
                if game.name and search_term in game.name.lower():
                    results.append(SteamApp(appid=game.appid, name=game.name))
            return results
        else:
            # Search full app list (this can be slow)
            all_apps = await self.get_app_list()
            return [app for app in all_apps if search_term in app.name.lower()]

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
