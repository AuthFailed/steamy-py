"""Store endpoints (steam.store): app details, the app list, search and news."""

import logging
from collections.abc import AsyncIterator
from typing import Any

from ..exceptions import (
    ResponseParsingError,
    SteamAPIError,
)
from ..models.game import (
    AppDetails,
    AppListResponse,
    GetAppListResponse,
    OwnedGame,
    SteamApp,
)
from ..models.stats import GetNewsResponse, NewsItem
from ..steamid import validate_app_id
from .base import BaseAPI

logger = logging.getLogger(__name__)


class StoreAPI(BaseAPI):
    """The Steam store: app details, the app list, store search and news."""

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

        with self._errors("get app details"):
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

            return AppDetails.model_validate(app_data.get("data"))

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

        with self._errors("get app list"):
            response_data = await self._request(
                interface="IStoreService",
                method="GetAppList",
                version="v1",
                auth_type="any",
                input_json=params,
            )

            if "response" not in response_data:
                raise ResponseParsingError("Invalid response structure from Steam API")

            return GetAppListResponse.model_validate(response_data).response

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

    async def get_news_for_app(
        self,
        app_id: int,
        count: int = 20,
        max_length: int = 300,
        end_date: int | None = None,
        feeds: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> list[NewsItem]:
        """Get news items for a game.

        Args:
            app_id: Steam App ID
            count: Number of news items to return (Steam's default is 20)
            max_length: Maximum length of each item's contents; longer
                contents are truncated. 0 returns the full contents.
            end_date: Only return items published before this Unix
                timestamp (use the last item's ``date`` to page)
            feeds: Only return items from these feed names
            tags: Only return items with these tags

        Returns:
            List of news items

        Raises:
            InvalidAppIDError: If App ID is invalid
            SteamAPIError: On API errors
        """
        validate_app_id(app_id)

        params = {
            "appid": str(app_id),
            "count": str(count),
            "maxlength": str(max_length),
        }
        if end_date is not None:
            params["enddate"] = str(end_date)
        if feeds:
            params["feeds"] = ",".join(feeds)
        if tags:
            params["tags"] = ",".join(tags)

        with self._errors("get news"):
            response_data = await self._request(
                interface="ISteamNews",
                method="GetNewsForApp",
                version="v2",
                auth_type="none",
                params=params,
            )

            if "appnews" not in response_data:
                return []

            response_obj = GetNewsResponse.model_validate(response_data)
            return response_obj.to_news_items()
