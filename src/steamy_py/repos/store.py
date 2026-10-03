"""Store endpoints (steam.store): app details, the app list, search and news."""

import logging
from collections.abc import AsyncIterator, Iterable, Mapping
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
from ..models.store import (
    SearchSuggestions,
    SearchSuggestionsResponse,
    StoreItems,
    StoreItemsResponse,
    StoreSearchResult,
)
from ..steamid import validate_app_id
from .base import BaseAPI

logger = logging.getLogger(__name__)

# ``steam_realm`` of the global Steam store (as opposed to Steam China).
_GLOBAL_REALM = 1


def _store_context(language: str, country_code: str) -> dict[str, Any]:
    """A StoreBrowseContext: the language and country to answer for."""
    return {
        "language": language,
        "country_code": country_code,
        "steam_realm": _GLOBAL_REALM,
    }


def _validate_app_ids(appids: Any) -> list[int]:
    """Validate one App ID or several; a str or bytes counts as one (invalid) id."""
    if isinstance(appids, str | bytes | bytearray) or not isinstance(appids, Iterable):
        appids = [appids]
    return [validate_app_id(appid) for appid in appids]


def _data_request(include_tag_count: int | None, **flags: bool) -> dict[str, Any]:
    """A StoreBrowseItemDataRequest asking for the parts whose flag is set."""
    request: dict[str, Any] = {name: True for name, wanted in flags.items() if wanted}
    if include_tag_count:
        request["include_tag_count"] = include_tag_count
    return request


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

    async def get_items(
        self,
        appids: int | Iterable[int],
        *,
        language: str = "english",
        country_code: str = "US",
        include_basic_info: bool = True,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_ratings: bool = False,
        include_tag_count: int | None = None,
        include_reviews: bool = False,
        include_all_purchase_options: bool = False,
        include_screenshots: bool = False,
        include_trailers: bool = False,
        include_supported_languages: bool = False,
        include_full_description: bool = False,
        include_links: bool = False,
    ) -> StoreItems:
        """Get store data for apps (IStoreBrowseService/GetItems).

        Needs no credential. The ``include_*`` flags choose which optional
        parts Steam fills in; parts not asked for, or that Steam has no
        data for, keep their defaults. Check each item's ``success`` (1)
        and ``visible`` before using it.

        Args:
            appids: One App ID or several
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and availability, e.g. "DE"
            include_basic_info: Short description, publishers, developers
                and franchises (``basic_info``)
            include_assets: Capsule, header and background image names
                (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_ratings: Age rating (``game_rating``)
            include_tag_count: Return up to this many weighted tags (``tags``)
            include_reviews: Review summaries (``reviews``)
            include_all_purchase_options: Every package and bundle that
                grants the app (``purchase_options``)
            include_screenshots: Screenshots (``screenshots``)
            include_trailers: Trailers (``trailers``, raw JSON)
            include_supported_languages: Languages and their audio and
                subtitle support (``supported_languages``)
            include_full_description: The store page text
                (``full_description``)
            include_links: Social media links (``links``)

        Returns:
            The items, in ``store_items``

        Raises:
            InvalidAppIDError: If an App ID is invalid
            ValueError: If no App ID is given
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        ids = [{"appid": appid} for appid in _validate_app_ids(appids)]
        if not ids:
            raise ValueError("At least one App ID must be provided")

        data_request = _data_request(
            include_tag_count,
            include_basic_info=include_basic_info,
            include_assets=include_assets,
            include_release=include_release,
            include_platforms=include_platforms,
            include_ratings=include_ratings,
            include_reviews=include_reviews,
            include_all_purchase_options=include_all_purchase_options,
            include_screenshots=include_screenshots,
            include_trailers=include_trailers,
            include_supported_languages=include_supported_languages,
            include_full_description=include_full_description,
            include_links=include_links,
        )
        with self._errors("get store items"):
            data = await self._request(
                "IStoreBrowseService",
                "GetItems",
                "v1",
                auth_type="none",
                input_json={
                    "ids": ids,
                    "context": _store_context(language, country_code),
                    "data_request": data_request,
                },
            )
            return StoreItemsResponse.model_validate(data).response

    async def search_suggestions(
        self,
        search_term: str,
        *,
        max_results: int = 10,
        language: str = "english",
        country_code: str = "US",
        use_spellcheck: bool = False,
        search_tags: bool = False,
        search_creators: bool = False,
        filters: Mapping[str, Any] | None = None,
        include_basic_info: bool = True,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_reviews: bool = False,
        include_tag_count: int | None = None,
    ) -> SearchSuggestions:
        """Get the store search box's suggestions for a term.

        Calls IStoreQueryService/SearchSuggestions; needs no credential.

        Args:
            search_term: What the user typed, e.g. "portal"
            max_results: Maximum number of suggestions
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and availability, e.g. "DE"
            use_spellcheck: Also match likely misspellings of the term
            search_tags: Also suggest store tags
            search_creators: Also suggest publishers, developers and
                franchises
            filters: A ``CStoreQueryFilters`` message, sent as given, e.g.
                ``{"released_only": True, "type_filters": {"include_games":
                True}}``
            include_basic_info: Short description, publishers, developers
                and franchises (``basic_info``)
            include_assets: Capsule and header image names (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_reviews: Review summaries (``reviews``)
            include_tag_count: Return up to this many weighted tags (``tags``)

        Returns:
            The matches in ``ids``, their data in ``store_items``

        Raises:
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        inputs: dict[str, Any] = {
            "context": _store_context(language, country_code),
            "search_term": search_term,
            "max_results": max_results,
            "data_request": _data_request(
                include_tag_count,
                include_basic_info=include_basic_info,
                include_assets=include_assets,
                include_release=include_release,
                include_platforms=include_platforms,
                include_reviews=include_reviews,
            ),
            "use_spellcheck": use_spellcheck,
            "search_tags": search_tags,
            "search_creators": search_creators,
        }
        if filters is not None:
            inputs["filters"] = dict(filters)

        with self._errors("get search suggestions"):
            data = await self._request(
                "IStoreQueryService",
                "SearchSuggestions",
                "v1",
                auth_type="none",
                input_json=inputs,
            )
            return SearchSuggestionsResponse.model_validate(data).response

    async def store_search(
        self, term: str, *, language: str = "english", country_code: str = "US"
    ) -> StoreSearchResult:
        """Search the store by name (store.steampowered.com/api/storesearch).

        Needs no credential. Prices are for the given country; free apps
        have none.

        Args:
            term: Search term, e.g. "portal"
            language: Language of the results, e.g. "german"
            country_code: Country for prices, e.g. "DE"

        Returns:
            The matching apps

        Raises:
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        with self._errors("search the store"):
            data = await self._request_store(
                "storesearch/",
                params={"term": term, "l": language, "cc": country_code},
                auth_type="none",
            )
            return StoreSearchResult.model_validate(data)
