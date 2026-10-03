"""Store endpoints (steam.store): apps and packages, store items, search,
charts, tags, reviews, the app list and news."""

import logging
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Any, overload

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
    AppDLCList,
    AppReview,
    AppReviews,
    CommunityApp,
    CommunityAppsResponse,
    DLCForApps,
    DLCForAppsResponse,
    DLCForAppsSolrResponse,
    GamesByConcurrentPlayers,
    GamesByConcurrentPlayersResponse,
    GamesFollowedResponse,
    ItemsToFeature,
    ItemsToFeatureResponse,
    MostPlayedGames,
    MostPlayedGamesResponse,
    PackageDetails,
    SearchSuggestions,
    SearchSuggestionsResponse,
    StoreCategoriesResponse,
    StoreCategory,
    StoreItems,
    StoreItemsResponse,
    StoreQueryResponse,
    StoreQueryResult,
    StoreSearchResult,
    TagList,
    TagListResponse,
    UserGameInterestState,
    UserGameInterestStateResponse,
    WeeklyTopSellers,
    WeeklyTopSellersResponse,
)
from ..steamid import SteamIDLike, validate_app_id, validate_steam_id
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


def _item_data_request(
    include_tag_count: int | None, **flags: bool
) -> dict[str, Any] | None:
    """A StoreBrowseItemDataRequest, or None when no part is asked for.

    Steam fills in store items only when a data request is sent, so leaving
    it out keeps them empty.
    """
    return _data_request(include_tag_count, **flags) or None


def _without_none(inputs: Mapping[str, Any]) -> dict[str, Any]:
    """``inputs`` without the entries that are None (left out of the request)."""
    return {name: value for name, value in inputs.items() if value is not None}


_INT32_MAX = 2**31 - 1


def _positive_ids(values: Any, what: str) -> list[int] | None:
    """Check optional ids (one int or several, each a positive int32, not a
    ``bool``); None or no ids gives None, and a str or bytes is rejected."""
    if values is None:
        return None
    if isinstance(values, str | bytes | bytearray) or not isinstance(values, Iterable):
        values = [values]
    ids = []
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 < value <= _INT32_MAX
        ):
            raise ValueError(f"Invalid {what}: {value!r}")
        ids.append(int(value))
    return ids or None


# ``CStoreQueryFilters_TypeFilters`` has an ``include_<type>`` flag for each.
_QUERY_ITEM_TYPES = (
    "apps",
    "packages",
    "bundles",
    "games",
    "demos",
    "mods",
    "dlc",
    "software",
    "video",
    "hardware",
    "series",
    "music",
)


def _type_filters(
    item_types: str | Iterable[str] | None, dlc_for_appid: int | None
) -> dict[str, Any] | None:
    """A CStoreQueryFilters_TypeFilters, or None when nothing is filtered."""
    if isinstance(item_types, str):
        item_types = [item_types]
    filters: dict[str, Any] = {}
    for item_type in item_types or ():
        if item_type not in _QUERY_ITEM_TYPES:
            raise ValueError(
                f"Unknown item type {item_type!r}; expected one of "
                + ", ".join(_QUERY_ITEM_TYPES)
            )
        filters[f"include_{item_type}"] = True
    if dlc_for_appid is not None:
        filters["dlc_for_appid"] = validate_app_id(dlc_for_appid)
    return filters or None


class StoreAPI(BaseAPI):
    """The Steam store: apps, packages, items, search, charts, reviews and news."""

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

    async def get_games_by_concurrent_players(
        self,
        *,
        language: str = "english",
        country_code: str = "US",
        include_basic_info: bool = False,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_reviews: bool = False,
        include_tag_count: int | None = None,
    ) -> GamesByConcurrentPlayers:
        """Get the games with the most players in game right now.

        Calls ISteamChartsService/GetGamesByConcurrentPlayers; needs no
        credential. Steam answers with its top 100. Each rank's ``item`` is
        filled in only when an ``include_*`` option asks for store data.

        Args:
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and availability, e.g. "DE"
            include_basic_info: Fill in ``item`` with names, short
                description, publishers and developers (``basic_info``)
            include_assets: Capsule and header image names (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_reviews: Review summaries (``reviews``)
            include_tag_count: Return up to this many weighted tags (``tags``)

        Returns:
            When the counts were taken (``last_update``) and the ranks

        Raises:
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        inputs = _without_none(
            {
                "context": _store_context(language, country_code),
                "data_request": _item_data_request(
                    include_tag_count,
                    include_basic_info=include_basic_info,
                    include_assets=include_assets,
                    include_release=include_release,
                    include_platforms=include_platforms,
                    include_reviews=include_reviews,
                ),
            }
        )
        with self._errors("get games by concurrent players"):
            data = await self._request(
                "ISteamChartsService",
                "GetGamesByConcurrentPlayers",
                "v1",
                auth_type="none",
                input_json=inputs,
            )
            return GamesByConcurrentPlayersResponse.model_validate(data).response

    async def get_most_played_games(
        self,
        *,
        language: str = "english",
        country_code: str = "US",
        include_basic_info: bool = False,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_reviews: bool = False,
        include_tag_count: int | None = None,
    ) -> MostPlayedGames:
        """Get Steam's most played games chart.

        Calls ISteamChartsService/GetMostPlayedGames; needs no credential.
        Each rank's ``item`` is filled in only when an ``include_*`` option
        asks for store data.

        Args:
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and availability, e.g. "DE"
            include_basic_info: Fill in ``item`` with names, short
                description, publishers and developers (``basic_info``)
            include_assets: Capsule and header image names (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_reviews: Review summaries (``reviews``)
            include_tag_count: Return up to this many weighted tags (``tags``)

        Returns:
            The chart's date (``rollup_date``) and its ranks

        Raises:
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        inputs = _without_none(
            {
                "context": _store_context(language, country_code),
                "data_request": _item_data_request(
                    include_tag_count,
                    include_basic_info=include_basic_info,
                    include_assets=include_assets,
                    include_release=include_release,
                    include_platforms=include_platforms,
                    include_reviews=include_reviews,
                ),
            }
        )
        with self._errors("get most played games"):
            data = await self._request(
                "ISteamChartsService",
                "GetMostPlayedGames",
                "v1",
                auth_type="none",
                input_json=inputs,
            )
            return MostPlayedGamesResponse.model_validate(data).response

    async def get_dlc_for_apps(
        self, appids: int | Iterable[int], *, country_code: str | None = None
    ) -> DLCForApps:
        """Get the DLC of apps, with the signed-in user's playtime in them.

        Calls IStoreBrowseService/GetDLCForApps with the access token; the
        user is the token's owner.

        Args:
            appids: One App ID or several
            country_code: Country for prices, e.g. "DE"; when None no store
                context is sent and Steam picks the country (unverified:
                presumably the user's)

        Returns:
            The DLC (``dlc_data``) and the user's playtime per app
            (``playtime``). Units of ``price``, ``discount`` and
            ``playtime`` are unverified.

        Raises:
            InvalidAppIDError: If an App ID is invalid
            ValueError: If no App ID is given
            AuthenticationError: If no access token is set
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        ids = [{"appid": appid} for appid in _validate_app_ids(appids)]
        if not ids:
            raise ValueError("At least one App ID must be provided")

        inputs: dict[str, Any] = {"appids": ids}
        if country_code is not None:
            inputs["context"] = {
                "country_code": country_code,
                "steam_realm": _GLOBAL_REALM,
            }
        with self._errors("get DLC for apps"):
            data = await self._request(
                "IStoreBrowseService",
                "GetDLCForApps",
                "v1",
                auth_type="access_token",
                input_json=inputs,
            )
            return DLCForAppsResponse.model_validate(data).response

    async def get_dlc_for_apps_solr(
        self,
        appids: int | Iterable[int],
        *,
        flavor: str | None = None,
        count: int | None = None,
        language: str = "english",
        country_code: str = "US",
    ) -> list[AppDLCList]:
        """Get the DLC app ids of apps.

        Calls IStoreBrowseService/GetDLCForAppsSolr; needs no credential.

        Args:
            appids: One App ID or several
            flavor: Passed to Steam as is; Steam does not document its
                values (unverified: a list ordering)
            count: Passed to Steam as is (unverified: the most DLC to return
                per app)
            language: Language of the store context, e.g. "german"
            country_code: Country of the store context, e.g. "DE"

        Returns:
            One list of DLC app ids per app Steam answers for

        Raises:
            InvalidAppIDError: If an App ID is invalid
            ValueError: If no App ID is given
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        ids = _validate_app_ids(appids)
        if not ids:
            raise ValueError("At least one App ID must be provided")

        inputs = _without_none(
            {
                "context": _store_context(language, country_code),
                "appids": ids,
                "flavor": flavor,
                "count": count,
            }
        )
        with self._errors("get DLC lists"):
            data = await self._request(
                "IStoreBrowseService",
                "GetDLCForAppsSolr",
                "v1",
                auth_type="none",
                input_json=inputs,
            )
            return DLCForAppsSolrResponse.model_validate(data).response.dlc_lists

    async def get_store_categories(
        self, *, language: str = "english", elanguage: int | None = None
    ) -> list[StoreCategory]:
        """Get the store's categories (IStoreBrowseService/GetStoreCategories).

        Needs no credential. The category ids are the ones in
        ``StoreItem.categories``.

        Args:
            language: Language of the display names, e.g. "german"
            elanguage: The language as an ELanguage number instead; left out
                when None

        Returns:
            The categories

        Raises:
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        response = await self._call_service(
            "IStoreBrowseService",
            "GetStoreCategories",
            "get store categories",
            {"language": language, "elanguage": elanguage},
            model=StoreCategoriesResponse,
            auth_type="none",
        )
        return response.response.categories

    async def get_items_to_feature(
        self,
        *,
        language: str = "english",
        country_code: str = "US",
        include_spotlights: bool = False,
        spotlight_location: str | None = None,
        spotlight_category: str | None = None,
        spotlight_genre_id: int | None = None,
        include_dailydeals: bool = False,
        include_top_specials_count: int | None = None,
        include_purchase_recommendations: bool = False,
        include_basic_info: bool = False,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_reviews: bool = False,
        include_tag_count: int | None = None,
    ) -> ItemsToFeature:
        """Get the items the store features: spotlights, deals and specials.

        Calls IStoreMarketingService/GetItemsToFeature; needs no credential
        and sends none. Each list is filled only when asked for, and each
        capsule's ``item`` only when an ``include_*`` data option is set.

        Args:
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and availability, e.g. "DE"
            include_spotlights: Return spotlights (``spotlights``)
            spotlight_location: Spotlight filter, passed as is (Steam does
                not document its values); implies ``include_spotlights``
            spotlight_category: Spotlight filter, passed as is; implies
                ``include_spotlights``
            spotlight_genre_id: Spotlight filter, passed as is; implies
                ``include_spotlights``
            include_dailydeals: Return the daily deals (``daily_deals``)
            include_top_specials_count: Return up to this many specials
                (``specials``)
            include_purchase_recommendations: Return purchase
                recommendations (``purchase_recommendations``; unverified:
                probably empty without a signed-in user)
            include_basic_info: Fill in items with names, short description,
                publishers and developers (``basic_info``)
            include_assets: Capsule and header image names (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_reviews: Review summaries (``reviews``)
            include_tag_count: Return up to this many weighted tags (``tags``)

        Returns:
            The featured items

        Raises:
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        spotlight_filter = _without_none(
            {
                "location": spotlight_location,
                "category": spotlight_category,
                "genre_id": spotlight_genre_id,
            }
        )
        inputs: dict[str, Any] = _without_none(
            {
                "context": _store_context(language, country_code),
                "data_request": _item_data_request(
                    include_tag_count,
                    include_basic_info=include_basic_info,
                    include_assets=include_assets,
                    include_release=include_release,
                    include_platforms=include_platforms,
                    include_reviews=include_reviews,
                ),
                "include_top_specials_count": include_top_specials_count,
            }
        )
        if include_spotlights or spotlight_filter:
            inputs["include_spotlights"] = spotlight_filter
        if include_dailydeals:
            inputs["include_dailydeals"] = True
        if include_purchase_recommendations:
            inputs["include_purchase_recommendations"] = True

        with self._errors("get items to feature"):
            data = await self._request(
                "IStoreMarketingService",
                "GetItemsToFeature",
                "v1",
                auth_type="none",
                input_json=inputs,
            )
            return ItemsToFeatureResponse.model_validate(data).response

    async def query(
        self,
        *,
        start: int = 0,
        count: int = 10,
        sort: int | None = None,
        released_only: bool = False,
        coming_soon_only: bool = False,
        item_types: str | Iterable[str] | None = None,
        dlc_for_appid: int | None = None,
        tagids_must_match: int | Iterable[int] | None = None,
        tagids_exclude: int | Iterable[int] | None = None,
        only_free_items: bool = False,
        exclude_free_items: bool = False,
        min_discount_percent: int | None = None,
        content_descriptors_must_match: int | Iterable[int] | None = None,
        content_descriptors_excluded: int | Iterable[int] | None = None,
        filters: Mapping[str, Any] | None = None,
        query_name: str | None = None,
        language: str = "english",
        country_code: str = "US",
        override_country_code: str | None = None,
        include_basic_info: bool = True,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_reviews: bool = False,
        include_tag_count: int | None = None,
    ) -> StoreQueryResult:
        """Search the store catalog with filters (IStoreQueryService/Query).

        Needs no credential. Filters left at their defaults are not sent.
        Page with ``start`` and ``count``; ``metadata.total_matching_records``
        counts all matches.

        Args:
            start: Index of the first match to return
            count: Number of matches to return (Steam's default is 10)
            sort: Result order as Steam's sort enum number; Steam does not
                publish the enum, and None leaves Steam's default
            released_only: Only released items
            coming_soon_only: Only items not released yet
            item_types: Only these kinds of items: one or several of "apps",
                "packages", "bundles", "games", "demos", "mods", "dlc",
                "software", "video", "hardware", "series", "music"
            dlc_for_appid: Only DLC for this app
            tagids_must_match: Only items with every one of these tag ids;
                each is sent as its own tag filter (unverified: Steam does
                not document how several tag filters combine)
            tagids_exclude: No items with any of these tag ids
            only_free_items: Only free items
            exclude_free_items: No free items
            min_discount_percent: Only items discounted at least this much
            content_descriptors_must_match: Only items with these content
                descriptor ids
            content_descriptors_excluded: No items with these content
                descriptor ids
            filters: Further ``CStoreQueryFilters`` fields, sent as given and
                merged over the ones above (its keys win), e.g.
                ``{"parent_appids": [620]}``
            query_name: Name of the query, used in Steam's logs and metrics
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and availability, e.g. "DE"
            override_country_code: Take the data from this country instead
            include_basic_info: Short description, publishers, developers
                and franchises (``basic_info``)
            include_assets: Capsule and header image names (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_reviews: Review summaries (``reviews``)
            include_tag_count: Return up to this many weighted tags (``tags``)

        Returns:
            The matches in ``ids``, their data in ``store_items``. With every
            ``include_*`` option off no data request is sent (unverified:
            ``store_items`` is then presumably empty)

        Raises:
            InvalidAppIDError: If ``dlc_for_appid`` is invalid
            ValueError: If an item type, tag id or content descriptor id is
                invalid
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        must_match = _positive_ids(tagids_must_match, "tag id")
        price_filters = _without_none(
            {
                "only_free_items": only_free_items or None,
                "exclude_free_items": exclude_free_items or None,
                "min_discount_percent": min_discount_percent,
            }
        )
        query_filters = _without_none(
            {
                "released_only": released_only or None,
                "coming_soon_only": coming_soon_only or None,
                "type_filters": _type_filters(item_types, dlc_for_appid),
                "tagids_must_match": (
                    None
                    if must_match is None
                    else [{"tagids": [tagid]} for tagid in must_match]
                ),
                "tagids_exclude": _positive_ids(tagids_exclude, "tag id"),
                "price_filters": price_filters or None,
                "content_descriptors_must_match": _positive_ids(
                    content_descriptors_must_match, "content descriptor id"
                ),
                "content_descriptors_excluded": _positive_ids(
                    content_descriptors_excluded, "content descriptor id"
                ),
            }
        )
        query_filters.update(filters or {})
        inputs = _without_none(
            {
                "query_name": query_name,
                "query": _without_none(
                    {
                        "start": start,
                        "count": count,
                        "sort": sort,
                        "filters": query_filters or None,
                    }
                ),
                "context": _store_context(language, country_code),
                "data_request": _item_data_request(
                    include_tag_count,
                    include_basic_info=include_basic_info,
                    include_assets=include_assets,
                    include_release=include_release,
                    include_platforms=include_platforms,
                    include_reviews=include_reviews,
                ),
                "override_country_code": override_country_code,
            }
        )
        with self._errors("query the store"):
            data = await self._request(
                "IStoreQueryService",
                "Query",
                "v1",
                auth_type="none",
                input_json=inputs,
            )
            return StoreQueryResponse.model_validate(data).response

    async def get_weekly_top_sellers(
        self,
        *,
        chart_country_code: str | None = None,
        language: str = "english",
        country_code: str = "US",
        start_date: int | None = None,
        page_start: int | None = None,
        page_count: int | None = None,
        include_basic_info: bool = False,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_reviews: bool = False,
        include_tag_count: int | None = None,
    ) -> WeeklyTopSellers:
        """Get one page of a week's top sellers chart.

        Calls IStoreTopSellersService/GetWeeklyTopSellers; needs no
        credential. Each rank's ``item`` is filled in only when an
        ``include_*`` option asks for store data.

        Args:
            chart_country_code: Country whose chart to return, e.g. "KR"
                (Steam's top-level ``country_code`` input). None leaves it
                out, as the store's global charts page does; Steam describes
                that as the global chart, but a published real reply to a
                request without it and with a "KR" context held the Korean
                chart, so the chart may then follow ``country_code``
                (unverified)
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and availability, e.g. "DE"
                (the store context); see ``chart_country_code``
            start_date: Start of the week to return (Unix time); None for
                the current week
            page_start: Index of the first rank to return; pass the previous
                page's ``next_page_start``
            page_count: Number of ranks per page; None leaves it to Steam.
                The proto declares 20, but real replies to requests without
                it held 10 ranks; the store's charts page asks for 20
            include_basic_info: Fill in ``item`` with names, short
                description, publishers and developers (``basic_info``)
            include_assets: Capsule and header image names (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_reviews: Review summaries (``reviews``)
            include_tag_count: Return up to this many weighted tags (``tags``)

        Returns:
            The week (``start_date``), its ranks and ``next_page_start``

        Raises:
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        inputs = _without_none(
            {
                "country_code": chart_country_code,
                "context": _store_context(language, country_code),
                "data_request": _item_data_request(
                    include_tag_count,
                    include_basic_info=include_basic_info,
                    include_assets=include_assets,
                    include_release=include_release,
                    include_platforms=include_platforms,
                    include_reviews=include_reviews,
                ),
                "start_date": start_date,
                "page_start": page_start,
                "page_count": page_count,
            }
        )
        with self._errors("get weekly top sellers"):
            data = await self._request(
                "IStoreTopSellersService",
                "GetWeeklyTopSellers",
                "v1",
                auth_type="none",
                input_json=inputs,
            )
            return WeeklyTopSellersResponse.model_validate(data).response

    async def get_community_apps(
        self, appids: int | Iterable[int], language: int | None = None
    ) -> list[CommunityApp]:
        """Get the Steam Community's data on apps: names, icons, content
        descriptors.

        Calls ICommunityService/GetApps without a credential. Steam does not
        document whether one is needed; several published clients call it
        without one, so this method sends none (not verified against Steam
        from here).

        Args:
            appids: One App ID or several
            language: Language of the names as an ELanguage number (0 is
                English), not a name like "english"; None leaves it out and
                Steam chooses

        Returns:
            The apps Steam answers for; unverified: unknown App IDs are left
            out

        Raises:
            InvalidAppIDError: If an App ID is invalid
            ValueError: If no App ID is given, or ``language`` is not an
                ELanguage number
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        ids = _validate_app_ids(appids)
        if not ids:
            raise ValueError("At least one App ID must be provided")

        response = await self._call_service(
            "ICommunityService",
            "GetApps",
            "get community apps",
            {"appids": ids, "language": _elanguage(language)},
            model=CommunityAppsResponse,
            auth_type="none",
        )
        return response.response.apps

    async def get_games_followed(self, steamid: SteamIDLike) -> list[int]:
        """Get the apps a user follows on the store.

        Calls IStoreService/GetGamesFollowed without a credential: Steam's
        public API list gives ``steamid`` as its only input. Published
        clients note that it needs the user's profile to be public; what
        Steam answers for a private one is unverified.

        Args:
            steamid: Steam ID of the user (int, str or SteamID)

        Returns:
            The App IDs of the followed apps; empty when Steam sends none

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        response = await self._call_service(
            "IStoreService",
            "GetGamesFollowed",
            "get followed games",
            {"steamid": validate_steam_id(steamid)},
            model=GamesFollowedResponse,
            auth_type="none",
        )
        return response.response.appids

    async def get_tag_list(
        self, language: str = "english", have_version_hash: str | None = None
    ) -> TagList:
        """Get every store tag with its name (IStoreService/GetTagList).

        Needs no credential and sends none. The tag ids are the ones in
        ``StoreItem.tagids`` and ``StoreItem.tags``.

        Args:
            language: Language of the names, e.g. "german"
            have_version_hash: The ``version_hash`` of a list fetched before;
                Steam then sends no tags if the list has not changed. None
                leaves it out

        Returns:
            The tags and the list's ``version_hash``. ``tags`` is empty when
            the list matches ``have_version_hash`` (unverified: whether
            ``version_hash`` is then sent)

        Raises:
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        response = await self._call_service(
            "IStoreService",
            "GetTagList",
            "get tag list",
            {"language": language, "have_version_hash": have_version_hash},
            model=TagListResponse,
            auth_type="none",
        )
        return response.response

    async def get_user_game_interest_state(
        self,
        appid: int,
        *,
        store_appid: int | None = None,
        beta_appid: int | None = None,
    ) -> UserGameInterestState:
        """Get the signed-in user's relationship to an app: ownership,
        wishlist, following, ignoring and discovery queues.

        Calls IStoreService/GetUserGameInterestState with the access token,
        which identifies the user, and never the API key. Steam takes it as a
        POST (xPaw's API data), so the inputs and the token go in the form
        body; it reads only and changes nothing.

        Args:
            appid: Steam App ID
            store_appid: Passed to Steam as is; Steam does not document it.
                Left out when None
            beta_appid: Passed to Steam as is; Steam does not document it
                (unverified: the app's playtest, for ``beta_status``). Left
                out when None

        Returns:
            The user's relationship to the app

        Raises:
            InvalidAppIDError: If an App ID is invalid
            AuthenticationError: If the client has no access token, or Steam
                rejects it
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        inputs = {
            "appid": validate_app_id(appid),
            "store_appid": _optional_app_id(store_appid),
            "beta_appid": _optional_app_id(beta_appid),
        }
        response = await self._call_service(
            "IStoreService",
            "GetUserGameInterestState",
            "get user game interest state",
            inputs,
            model=UserGameInterestStateResponse,
            http_method="POST",
            auth_type="access_token",
        )
        return response.response

    @overload
    async def get_package_details(
        self,
        packageids: int,
        *,
        country_code: str | None = None,
        language: str | None = None,
    ) -> PackageDetails | None: ...

    @overload
    async def get_package_details(
        self,
        packageids: Iterable[int],
        *,
        country_code: str | None = None,
        language: str | None = None,
    ) -> dict[int, PackageDetails]: ...

    async def get_package_details(
        self,
        packageids: int | Iterable[int],
        *,
        country_code: str | None = None,
        language: str | None = None,
    ) -> PackageDetails | dict[int, PackageDetails] | None:
        """Get store data for packages (store.steampowered.com/api/packagedetails).

        Needs no credential and sends none. Like ``get_app_details``, a
        package Steam answers without ``success`` (or does not answer for at
        all, or a body that is not a JSON object) counts as not found.
        Published clients ask for one package per request; whether Steam
        still answers several comma-separated ids in one request is
        unverified.

        Args:
            packageids: One package id (returns its details or None) or
                several (returns a dict)
            country_code: Country for prices, e.g. "DE" (``cc``); None leaves
                it out and Steam chooses
            language: Language of names, e.g. "german" (``l``); None leaves
                it out and Steam chooses

        Returns:
            For one int: the package's details, or None if not found. For
            several: package id -> details, without the packages not found

        Raises:
            ValueError: If no package id is given or one is not a positive
                32-bit int
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        ids = _package_ids(packageids)
        params = {"packageids": ",".join(str(packageid) for packageid in ids)}
        if country_code is not None:
            params["cc"] = country_code
        if language is not None:
            params["l"] = language

        found: dict[int, PackageDetails] = {}
        with self._errors("get package details"):
            data = await self._request_store(
                "packagedetails/", params=params, auth_type="none"
            )
            # As in get_app_details, a body that is not an object (appdetails
            # answers some ids with JSON null) means nothing was found.
            entries = data if isinstance(data, dict) else {}
            for packageid in ids:
                entry = entries.get(str(packageid))
                if isinstance(entry, dict) and entry.get("success"):
                    found[packageid] = PackageDetails.model_validate(entry.get("data"))

        if isinstance(packageids, int):
            return found.get(ids[0])
        return found

    async def get_app_reviews(
        self,
        appid: int,
        *,
        filter: str = "all",
        language: str = "all",
        day_range: int | None = None,
        cursor: str = "*",
        review_type: str = "all",
        purchase_type: str = "all",
        num_per_page: int = 20,
        filter_offtopic_activity: bool | None = None,
    ) -> AppReviews:
        """Get one page of an app's user reviews.

        Calls store.steampowered.com/appreviews/<appid>?json=1; needs no
        credential and sends none. Steam's documentation now marks this
        endpoint deprecated in favour of IUserReviewsService/GetAppReviews,
        which takes the same filters. Use ``iter_app_reviews`` to follow
        ``cursor`` through every page.

        Args:
            appid: Steam App ID
            filter: Order: "all" (most helpful), "recent" (newest first) or
                "updated" (last updated first). Steam documents that "all"
                widens ``day_range`` until it finds reviews, so paging
                through it may not run out; use "recent" or "updated" for
                that
            language: Language of the reviews, e.g. "english"; "all" for
                every language
            day_range: For "all" only: how many days back to look (Steam:
                at most 365); None leaves it to Steam
            cursor: "*" for the first page, then the ``cursor`` of the page
                before. Pass it as Steam sent it; it is URL-encoded here
            review_type: "all", "positive" or "negative"
            purchase_type: "all", "steam" or "non_steam_purchase"; Steam's
                own default is "steam"
            num_per_page: Reviews per page (Steam: at most 100)
            filter_offtopic_activity: Steam leaves out off-topic reviews
                ("review bombs") by default; False includes them. None
                leaves it to Steam

        Returns:
            The page; check ``success`` (1). The totals in ``query_summary``
            come only with the first page and only for ``review_type``
            "all" (Steam's documentation)

        Raises:
            InvalidAppIDError: If the App ID is invalid
            ValueError: If ``num_per_page`` or ``day_range`` is not a
                non-negative int
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        validate_app_id(appid)
        params = {
            "json": "1",
            "filter": filter,
            "language": language,
            "cursor": cursor,
            "review_type": review_type,
            "purchase_type": purchase_type,
            "num_per_page": _count(num_per_page, "num_per_page"),
        }
        if day_range is not None:
            params["day_range"] = _count(day_range, "day_range")
        if filter_offtopic_activity is not None:
            params["filter_offtopic_activity"] = (
                "1" if filter_offtopic_activity else "0"
            )

        with self._errors("get app reviews"):
            data = await self.client.request(
                "GET",
                self._store_page_url(f"appreviews/{appid}"),
                params=params,
                auth_type="none",
            )
            return AppReviews.model_validate(data)

    async def iter_app_reviews(
        self,
        appid: int,
        *,
        filter: str = "recent",
        language: str = "all",
        day_range: int | None = None,
        review_type: str = "all",
        purchase_type: str = "all",
        num_per_page: int = 100,
        filter_offtopic_activity: bool | None = None,
    ) -> AsyncIterator[AppReview]:
        """Iterate over an app's user reviews, one page request at a time.

        Follows ``cursor`` from "*" and stops at a page without reviews, or
        when Steam sends a cursor it sent before. The arguments are those of
        ``get_app_reviews``, but ``filter`` defaults to "recent" (Steam
        documents that only "recent" and "updated" run out of reviews) and
        ``num_per_page`` to Steam's maximum, 100.

        Yields:
            The reviews, page by page

        Raises:
            InvalidAppIDError: If the App ID is invalid
            ValueError: If ``num_per_page`` or ``day_range`` is not a
                non-negative int
            ResponseParsingError: If a response has an unexpected shape
            SteamAPIError: On API errors
        """
        cursor = "*"
        seen = {cursor}
        while True:
            page = await self.get_app_reviews(
                appid,
                filter=filter,
                language=language,
                day_range=day_range,
                cursor=cursor,
                review_type=review_type,
                purchase_type=purchase_type,
                num_per_page=num_per_page,
                filter_offtopic_activity=filter_offtopic_activity,
            )
            for review in page.reviews:
                yield review
            cursor = page.cursor
            if not page.reviews or not cursor or cursor in seen:
                return
            seen.add(cursor)

    def _store_page_url(self, path: str) -> str:
        """URL of a store page outside /api, e.g. "appreviews/620".

        The store root is ``STEAM_STORE_BASE_URL`` without its trailing
        "/api".
        """
        base = self.client.settings.STEAM_STORE_BASE_URL.rstrip("/")
        return f"{base.removesuffix('/api')}/{path.lstrip('/')}"


# -- helpers for the methods above -------------------------------------------------

_UINT32_MAX = 2**32 - 1


def _optional_app_id(value: int | None) -> int | None:
    """Validate an optional App ID input; None stays None (left out)."""
    return None if value is None else validate_app_id(value)


def _elanguage(value: int | None) -> int | None:
    """Check an optional ELanguage number (a non-negative ``int``, not a
    ``bool``); a language name such as "english" is rejected, since Steam
    takes a number here. None stays None (left out)."""
    if value is not None and (
        isinstance(value, bool) or not isinstance(value, int) or value < 0
    ):
        raise ValueError(f"language must be an ELanguage number: {value!r}")
    return value


def _count(value: int, name: str) -> str:
    """A non-negative ``int`` input (not a ``bool``) as a query value."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative int: {value!r}")
    return str(int(value))


def _package_ids(values: Any) -> list[int]:
    """Check one package id or several (each a positive 32-bit int, not a
    ``bool``), without duplicates; a str or bytes is rejected."""
    if isinstance(values, str | bytes | bytearray) or not isinstance(values, Iterable):
        values = [values]
    ids: list[int] = []
    for value in values:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 < value <= _UINT32_MAX
        ):
            raise ValueError(f"Invalid package id: {value!r}")
        ids.append(int(value))
    if not ids:
        raise ValueError("At least one package id must be provided")
    return list(dict.fromkeys(ids))
