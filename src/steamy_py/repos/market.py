"""Market API endpoints for Steam Community Market."""

import logging

from ..exceptions import (
    InvalidSteamIDError,
    PlayerNotFoundError,
    PrivateProfileError,
    SteamAPIError,
)
from ..models.market import (
    InventoryResponse,
    ItemPriceResponse,
    MarketHistoryEntry,
    MarketHistoryResponse,
    MarketListingsResponse,
    PriceInfo,
)
from .base import BaseAPI

logger = logging.getLogger(__name__)


class MarketAPI(BaseAPI):
    """Steam Community Market API endpoints."""

    def __init__(self, client):
        """Initialize Market API."""
        super().__init__(client)
        self.market_base_url = "https://steamcommunity.com/market"

    def _build_market_url(self, endpoint: str) -> str:
        """Build Steam Community Market URL.

        Args:
            endpoint: Market endpoint

        Returns:
            Complete market URL
        """
        endpoint = endpoint.lstrip("/")
        return f"{self.market_base_url}/{endpoint}"

    async def get_item_price(
        self,
        market_hash_name: str,
        app_id: int = 730,  # Default to CS:GO
        currency: int = 1,  # USD
    ) -> PriceInfo | None:
        """Get current market price for an item.

        Args:
            market_hash_name: Item's market hash name
            app_id: Steam App ID (default: 730 for CS:GO)
            currency: Currency code (1=USD, 3=EUR, etc.)

        Returns:
            Price information or None if not found

        Raises:
            SteamAPIError: On API errors
        """
        try:
            url = self._build_market_url("priceoverview/")

            # Market API doesn't require authentication for price data
            params = {
                "appid": str(app_id),
                "market_hash_name": market_hash_name,
                "currency": str(currency),
            }

            # Remove API key for market requests
            response_data = await self.client.request("GET", url, params=params)

            if not response_data.get("success"):
                return None

            response_obj = ItemPriceResponse(**response_data)
            return response_obj.to_price_info()

        except Exception as e:
            logger.error(f"Error getting price for '{market_hash_name}': {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get item price: {e}")

    async def get_market_listings(
        self, market_hash_name: str, app_id: int = 730, start: int = 0, count: int = 100
    ) -> MarketListingsResponse:
        """Get market listings for an item.

        Args:
            market_hash_name: Item's market hash name
            app_id: Steam App ID
            start: Starting index for pagination
            count: Number of results to return

        Returns:
            Market listings response

        Raises:
            SteamAPIError: On API errors
        """
        try:
            url = self._build_market_url("listings/")

            params = {
                "appid": str(app_id),
                "market_hash_name": market_hash_name,
                "start": str(start),
                "count": str(count),
                "currency": "1",  # USD
                "format": "json",
            }

            response_data = await self.client.request("GET", url, params=params)

            return MarketListingsResponse(**response_data)

        except Exception as e:
            logger.error(f"Error getting listings for '{market_hash_name}': {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get market listings: {e}")

    async def get_price_history(
        self, market_hash_name: str, app_id: int = 730
    ) -> list[MarketHistoryEntry]:
        """Get price history for an item.

        Args:
            market_hash_name: Item's market hash name
            app_id: Steam App ID

        Returns:
            List of price history entries

        Raises:
            SteamAPIError: On API errors
        """
        try:
            url = self._build_market_url("pricehistory/")

            params = {"appid": str(app_id), "market_hash_name": market_hash_name}

            response_data = await self.client.request("GET", url, params=params)

            if not response_data.get("success"):
                return []

            response_obj = MarketHistoryResponse(**response_data)
            return response_obj.to_history_entries()

        except Exception as e:
            logger.error(f"Error getting price history for '{market_hash_name}': {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get price history: {e}")

    async def get_inventory(
        self,
        steamid: str,
        app_id: int,
        context_id: str = "2",
        start_assetid: str | None = None,
        count: int = 5000,
    ) -> InventoryResponse:
        """Get Steam inventory for a user.

        Args:
            steamid: Steam ID of the user
            app_id: Steam App ID
            context_id: Inventory context ID (usually "2")
            start_assetid: Starting asset ID for pagination
            count: Maximum items to return

        Returns:
            Inventory response

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            PrivateProfileError: If inventory is private
            SteamAPIError: On API errors
        """
        self._validate_steam_id(steamid)

        try:
            url = (
                f"https://steamcommunity.com/inventory/{steamid}/{app_id}/{context_id}"
            )

            params = {"l": "english", "count": str(count)}

            if start_assetid:
                params["start_assetid"] = start_assetid

            response_data = await self.client.request("GET", url, params=params)

            # Check for common error responses
            if "error" in response_data:
                error_msg = response_data["error"]
                if "private" in error_msg.lower():
                    raise PrivateProfileError(steamid)
                elif "not found" in error_msg.lower():
                    raise PlayerNotFoundError(steamid)
                else:
                    raise SteamAPIError(f"Inventory error: {error_msg}")

            return InventoryResponse(**response_data)

        except (PrivateProfileError, PlayerNotFoundError):
            raise
        except Exception as e:
            logger.error(f"Error getting inventory for {steamid}: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to get inventory: {e}")

    async def search_market(
        self,
        query: str = "",
        app_id: int | None = None,
        start: int = 0,
        count: int = 100,
        sort_column: str = "popular",
        sort_dir: str = "desc",
    ) -> MarketListingsResponse:
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
        try:
            url = self._build_market_url("search/render/")

            params = {
                "query": query,
                "start": str(start),
                "count": str(count),
                "sort_column": sort_column,
                "sort_dir": sort_dir,
                "norender": "1",  # Get JSON instead of HTML
            }

            if app_id:
                params["category_730_ItemSet[]"] = "any"
                params["category_730_ProPlayer[]"] = "any"
                params["category_730_StickerCapsule[]"] = "any"
                params["category_730_TournamentTeam[]"] = "any"
                params["category_730_Weapon[]"] = "any"
                params["appid"] = str(app_id)

            response_data = await self.client.request("GET", url, params=params)

            return MarketListingsResponse(**response_data)

        except Exception as e:
            logger.error(f"Error searching market: {e}")
            if isinstance(e, SteamAPIError):
                raise
            raise SteamAPIError(f"Failed to search market: {e}")

    async def get_popular_items(
        self, app_id: int | None = None, count: int = 100
    ) -> MarketListingsResponse:
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

    async def get_recent_items(
        self, app_id: int | None = None, count: int = 100
    ) -> MarketListingsResponse:
        """Get recently listed market items.

        Args:
            app_id: Filter by app ID
            count: Number of results

        Returns:
            Recent items

        Raises:
            SteamAPIError: On API errors
        """
        return await self.search_market(
            query="",
            app_id=app_id,
            count=count,
            sort_column="quantity",
            sort_dir="desc",
        )

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
