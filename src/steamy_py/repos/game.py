"""Games/Apps API endpoints for Steam API."""

import logging
from collections.abc import AsyncIterator
from typing import Any

from ..exceptions import (
    GameNotFoundError,
    PrivateProfileError,
    SteamAPIError,
)
from ..models.game import (
    Achievement,
    AppDetails,
    AppListResponse,
    GameSchema,
    GetAppListResponse,
    GetOwnedGamesResponse,
    GetPlayerAchievementsResponse,
    GetSchemaResponse,
    OwnedGame,
    SteamApp,
)
from ..steamid import SteamIDLike, validate_app_id, validate_steam_id
from .base import BaseAPI

logger = logging.getLogger(__name__)


class GameAPI(BaseAPI):
    """Steam Games/Apps API endpoints."""

    async def get_owned_games(
        self,
        steamid: SteamIDLike,
        include_appinfo: bool = True,
        include_played_free_games: bool = False,
        appids_filter: list[int] | None = None,
        include_extended_appinfo: bool = False,
        include_free_sub: bool = False,
        skip_unvetted_apps: bool | None = None,
        include_family_licenses: bool = False,
        language: str | None = None,
    ) -> list[OwnedGame]:
        """Get games owned by a Steam user.

        Args:
            steamid: Steam ID of the user
            include_appinfo: Include game name and logo information
            include_played_free_games: Include free games that have been played
            appids_filter: Optional list of App IDs to filter results
            include_extended_appinfo: Include capsule, sort name and the
                has_workshop/market/dlc/leaderboards flags
            include_free_sub: Include games from free subscriptions
            skip_unvetted_apps: Skip apps that have not been vetted; Steam's
                default is used when None
            include_family_licenses: Include games shared through Steam Family
            language: Language for game names

        Returns:
            List of owned games

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            PrivateProfileError: If the game details are not public
            SteamAPIError: On API errors
        """
        steamid = validate_steam_id(steamid)

        params = {
            "steamid": steamid,
            "include_appinfo": "1" if include_appinfo else "0",
            "include_played_free_games": "1" if include_played_free_games else "0",
        }

        optional = {
            "include_extended_appinfo": "1" if include_extended_appinfo else None,
            "include_free_sub": "1" if include_free_sub else None,
            "skip_unvetted_apps": (
                None if skip_unvetted_apps is None else str(int(skip_unvetted_apps))
            ),
            "include_family_licenses": "1" if include_family_licenses else None,
            "language": language,
        }
        params.update({k: v for k, v in optional.items() if v is not None})
        if appids_filter:
            params.update(self._indexed("appids_filter", appids_filter))

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
            logger.error("Error getting owned games for %s: %s", steamid, e)
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get owned games: {e}") from e

    async def get_app_list_page(
        self,
        last_appid: int = 0,
        max_results: int = 10_000,
        *,
        include_games: bool = True,
        include_dlc: bool = True,
        include_software: bool = True,
        include_videos: bool = True,
        include_hardware: bool = True,
        if_modified_since: int | None = None,
        have_description_language: str | None = None,
    ) -> AppListResponse:
        """Get one page of Steam applications (IStoreService/GetAppList).

        Args:
            last_appid: Return apps after this App ID (0 for the first page)
            max_results: Page size; Steam allows up to 50,000
            include_games: Include games
            include_dlc: Include DLC
            include_software: Include software
            include_videos: Include videos and series
            include_hardware: Include hardware
            if_modified_since: Only apps changed after this Unix timestamp
            have_description_language: Only apps with a description in this
                language (e.g. "english")

        Returns:
            The page; pass its ``last_appid`` back while ``have_more_results``

        Raises:
            SteamAPIError: On API errors
        """
        params: dict[str, Any] = {
            "last_appid": last_appid,
            "max_results": max_results,
            "include_games": include_games,
            "include_dlc": include_dlc,
            "include_software": include_software,
            "include_videos": include_videos,
            "include_hardware": include_hardware,
        }
        if if_modified_since is not None:
            params["if_modified_since"] = if_modified_since
        if have_description_language is not None:
            params["have_description_language"] = have_description_language

        try:
            response_data = await self._request(
                interface="IStoreService",
                method="GetAppList",
                version="v1",
                input_json=params,
            )

            if "response" not in response_data:
                raise SteamAPIError("Invalid response structure from Steam API")

            return GetAppListResponse(**response_data).response

        except Exception as e:
            logger.error("Error getting app list: %s", e)
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get app list: {e}") from e

    async def iter_app_list(
        self, max_results: int = 10_000, **filters: Any
    ) -> AsyncIterator[SteamApp]:
        """Iterate over all Steam applications, one page request at a time.

        Args:
            max_results: Page size; Steam allows up to 50,000
            **filters: Filters accepted by ``get_app_list_page``

        Yields:
            Steam applications in App ID order

        Raises:
            SteamAPIError: On API errors
        """
        last_appid = 0
        while True:
            page = await self.get_app_list_page(last_appid, max_results, **filters)
            for app in page.apps:
                yield app
            if not page.have_more_results or not page.apps:
                return
            next_appid = page.last_appid or page.apps[-1].appid
            if next_appid <= last_appid:
                raise SteamAPIError("Steam returned the same app list page twice")
            last_appid = next_appid

    async def get_app_list(
        self, max_results: int = 10_000, **filters: Any
    ) -> list[SteamApp]:
        """Get all Steam applications (IStoreService/GetAppList).

        This pages through roughly 200,000 apps; prefer ``iter_app_list`` or
        ``get_app_list_page`` with ``if_modified_since`` for regular syncs.

        Args:
            max_results: Page size; Steam allows up to 50,000
            **filters: Filters accepted by ``get_app_list_page``

        Returns:
            List of Steam applications

        Raises:
            SteamAPIError: On API errors
        """
        return [app async for app in self.iter_app_list(max_results, **filters)]

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

        try:
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
                raise SteamAPIError("Invalid response structure from Steam API")

            playerstats = response_data["playerstats"]

            if not playerstats.get("success", False):
                self._raise_playerstats_error(
                    str(playerstats.get("error", "Unknown error")), steamid, app_id
                )

            response_obj = GetPlayerAchievementsResponse(**response_data)
            return response_obj.playerstats.achievements

        except (PrivateProfileError, GameNotFoundError):
            raise
        except Exception as e:
            logger.error(
                "Error getting achievements for %s, app %s: %s", steamid, app_id, e
            )
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
        validate_app_id(app_id)

        try:
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

            response_obj = GetSchemaResponse(**response_data)
            return response_obj.game

        except GameNotFoundError:
            raise
        except Exception as e:
            logger.error("Error getting schema for app %s: %s", app_id, e)
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
        validate_app_id(app_id)

        try:
            response_data = await self._request_store(
                endpoint="appdetails",
                params={"appids": str(app_id), "cc": country, "l": language},
            )

            # Steam answers some app ids with a JSON null body.
            if not isinstance(response_data, dict):
                return None
            app_data = response_data.get(str(app_id))
            if (
                not isinstance(app_data, dict)
                or not app_data
                or not app_data.get("success")
            ):
                return None

            return AppDetails(**app_data["data"])

        except Exception as e:
            logger.error("Error getting app details for %s: %s", app_id, e)
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

        if owned_games is not None:
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
