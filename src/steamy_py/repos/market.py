"""Market API endpoints for Steam Community Market.

These are unofficial steamcommunity.com endpoints, not part of the Steam Web
API. They need no API key (and must never receive one), and Steam rate limits
them much more aggressively than api.steampowered.com.
"""

import logging
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import quote

from ..exceptions import (
    AuthenticationError,
    SteamAPIError,
)
from ..models.market import (
    InventoryResponse,
    ItemPriceResponse,
    MarketHistoryEntry,
    MarketHistoryResponse,
    MarketListingsResponse,
    MarketSearchResponse,
    PriceInfo,
)
from ..steamid import SteamIDLike
from .base import BaseAPI
from .economy import INVENTORY_PAGE_SIZE, EconomyAPI

logger = logging.getLogger(__name__)


def _is_unsuccessful(body: Any) -> bool:
    """Whether ``body`` is Steam's ``{"success": false}`` reply."""
    return isinstance(body, dict) and body.get("success") in (False, 0)


class MarketAPI(BaseAPI):
    """Steam Community Market endpoints (steamcommunity.com)."""

    @property
    def community_base_url(self) -> str:
        """Base URL of the Steam Community site."""
        return self.client.settings.STEAM_COMMUNITY_BASE_URL.rstrip("/")

    @property
    def market_base_url(self) -> str:
        """Base URL of the Steam Community Market."""
        return f"{self.community_base_url}/market"

    def _build_market_url(self, endpoint: str) -> str:
        """Build Steam Community Market URL.

        Args:
            endpoint: Market endpoint

        Returns:
            Complete market URL
        """
        endpoint = endpoint.lstrip("/")
        return f"{self.market_base_url}/{endpoint}"

    async def _request_community(
        self, url: str, params: dict[str, Any], auth_type: str = "none"
    ) -> dict[str, Any]:
        """GET a steamcommunity.com URL; never sends the API key or token."""
        return await self.client.request("GET", url, params=params, auth_type=auth_type)

    async def get_item_price(
        self,
        market_hash_name: str,
        app_id: int = 730,  # Counter-Strike 2
        currency: int = 1,  # USD
    ) -> PriceInfo | None:
        """Get current market price for an item.

        Args:
            market_hash_name: Item's market hash name
            app_id: Steam App ID (default: 730, Counter-Strike 2)
            currency: Currency code (1=USD, 3=EUR, etc.)

        Returns:
            Price information or None if not found

        Raises:
            SteamAPIError: On API errors
        """
        with self._errors("get item price"):
            url = self._build_market_url("priceoverview/")

            params = {
                "appid": str(app_id),
                "market_hash_name": market_hash_name,
                "currency": str(currency),
            }

            try:
                response_data = await self._request_community(url, params)
            except SteamAPIError as e:
                # Steam answers an unknown item with HTTP 500 {"success": false}.
                if e.status_code == 500 and _is_unsuccessful(e.response_data):
                    return None
                raise

            if not response_data.get("success"):
                return None

            response_obj = ItemPriceResponse.model_validate(response_data)
            return response_obj.to_price_info()

    async def get_market_listings(
        self,
        market_hash_name: str,
        app_id: int = 730,
        start: int = 0,
        count: int = 100,
        currency: int = 1,
    ) -> MarketListingsResponse:
        """Get market listings for an item.

        Args:
            market_hash_name: Item's market hash name
            app_id: Steam App ID
            start: Starting index for pagination
            count: Number of results to return
            currency: Currency code (1=USD, 3=EUR, etc.)

        Returns:
            Market listings response

        Raises:
            SteamAPIError: On API errors
        """
        with self._errors("get market listings"):
            url = self._build_market_url(
                f"listings/{app_id}/{quote(market_hash_name, safe='')}/render/"
            )

            params = {
                "start": str(start),
                "count": str(count),
                "currency": str(currency),
                "format": "json",
            }

            response_data = await self._request_community(url, params)

            return MarketListingsResponse.model_validate(response_data)

    async def get_price_history(
        self, market_hash_name: str, app_id: int = 730
    ) -> list[MarketHistoryEntry]:
        """Get price history for an item.

        Steam only answers signed-in users: pass the ``steamLoginSecure``
        cookie of a steamcommunity.com session to ``Steam(steam_login_secure=...)``.

        Args:
            market_hash_name: Item's market hash name
            app_id: Steam App ID

        Returns:
            List of price history entries (empty if Steam reports no success)

        Raises:
            AuthenticationError: If no ``steamLoginSecure`` cookie is configured,
                or Steam rejects it
            SteamAPIError: On API errors
        """
        with self._errors("get price history"):
            url = self._build_market_url("pricehistory/")

            params = {"appid": str(app_id), "market_hash_name": market_hash_name}

            try:
                response_data = await self._request_community(
                    url, params, auth_type="cookie"
                )
            except SteamAPIError as e:
                # Steam answers an expired or invalid cookie with HTTP 400 []
                # or a redirect to the login page (never followed with a
                # credential).
                status = e.status_code
                if type(e) is SteamAPIError and (
                    (status == 400 and e.response_data == [])
                    or (status is not None and 300 <= status < 400)
                ):
                    raise AuthenticationError(
                        "Steam rejected the steamLoginSecure cookie",
                        status,
                        e.response_data,
                    ) from None
                raise

            if not isinstance(response_data, dict) or not response_data.get("success"):
                return []

            response_obj = MarketHistoryResponse.model_validate(response_data)
            return response_obj.to_history_entries()

    async def get_inventory(
        self,
        steamid: SteamIDLike,
        app_id: int,
        context_id: str = "2",
        start_assetid: str | None = None,
        count: int = INVENTORY_PAGE_SIZE,
        language: str = "english",
    ) -> InventoryResponse:
        """Deprecated: use ``Steam.economy.get_inventory``."""
        self._deprecated("MarketAPI.get_inventory", "Steam.economy.get_inventory")
        return await EconomyAPI(self.client).get_inventory(
            steamid, app_id, context_id, start_assetid, count, language
        )

    async def iter_inventory_pages(
        self,
        steamid: SteamIDLike,
        app_id: int,
        context_id: str = "2",
        count: int = INVENTORY_PAGE_SIZE,
        language: str = "english",
    ) -> AsyncIterator[InventoryResponse]:
        """Deprecated: use ``Steam.economy.iter_inventory_pages``."""
        self._deprecated(
            "MarketAPI.iter_inventory_pages", "Steam.economy.iter_inventory_pages"
        )
        async for page in EconomyAPI(self.client).iter_inventory_pages(
            steamid, app_id, context_id, count, language
        ):
            yield page

    async def get_full_inventory(
        self,
        steamid: SteamIDLike,
        app_id: int,
        context_id: str = "2",
        count: int = INVENTORY_PAGE_SIZE,
        language: str = "english",
    ) -> InventoryResponse:
        """Deprecated: use ``Steam.economy.get_full_inventory``."""
        self._deprecated(
            "MarketAPI.get_full_inventory", "Steam.economy.get_full_inventory"
        )
        return await EconomyAPI(self.client).get_full_inventory(
            steamid, app_id, context_id, count, language
        )

    async def search_market(
        self,
        query: str = "",
        app_id: int | None = None,
        start: int = 0,
        count: int = 100,
        sort_column: str = "popular",
        sort_dir: str = "desc",
    ) -> MarketSearchResponse:
        """Search the Steam Community Market.

        Args:
            query: Search query
            app_id: Filter by app ID
            start: Starting index for pagination
            count: Number of results
            sort_column: Sort column (popular, price, name)
            sort_dir: Sort direction (asc, desc)

        Returns:
            Market search results

        Raises:
            SteamAPIError: On API errors
        """
        with self._errors("search market"):
            url = self._build_market_url("search/render/")

            params = {
                "query": query,
                "start": str(start),
                "count": str(count),
                "sort_column": sort_column,
                "sort_dir": sort_dir,
                "norender": "1",  # Get JSON instead of HTML
            }

            if app_id is not None:
                params["appid"] = str(app_id)

            response_data = await self._request_community(url, params)

            return MarketSearchResponse.model_validate(response_data)

    async def get_popular_items(
        self, app_id: int | None = None, count: int = 100
    ) -> MarketSearchResponse:
        """Get popular market items.

        Args:
            app_id: Filter by app ID
            count: Number of results

        Returns:
            Popular items

        Raises:
            SteamAPIError: On API errors
        """
        return await self.search_market(
            query="", app_id=app_id, count=count, sort_column="popular", sort_dir="desc"
        )
