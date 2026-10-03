"""Economy endpoints (steam.economy): community inventories.

The inventory endpoint is an unofficial steamcommunity.com page, not part of
the Web API: it needs no credential and is rate limited much more strictly.
"""

import logging
from collections.abc import AsyncIterator

from ..exceptions import (
    PlayerNotFoundError,
    PrivateProfileError,
    SteamAPIError,
)
from ..models.market import InventoryResponse
from ..steamid import SteamIDLike, validate_steam_id
from .base import BaseAPI

logger = logging.getLogger(__name__)

# Largest page Steam serves from /inventory/.
INVENTORY_PAGE_SIZE = 2000


class EconomyAPI(BaseAPI):
    """Items and inventories."""

    @property
    def community_base_url(self) -> str:
        """Base URL of the Steam Community site."""
        return self.client.settings.STEAM_COMMUNITY_BASE_URL.rstrip("/")

    async def get_inventory(
        self,
        steamid: SteamIDLike,
        app_id: int,
        context_id: str = "2",
        start_assetid: str | None = None,
        count: int = INVENTORY_PAGE_SIZE,
        language: str = "english",
    ) -> InventoryResponse:
        """Get one page of a user's Steam inventory.

        Use ``get_full_inventory`` or ``iter_inventory_pages`` for every page.

        Args:
            steamid: Steam ID of the user
            app_id: Steam App ID
            context_id: Inventory context ID (usually "2")
            start_assetid: Return items after this asset id (a previous
                page's ``last_assetid``)
            count: Maximum items to return; Steam allows up to 2000
            language: Language for item descriptions

        Returns:
            Inventory page; ``has_more_items`` tells whether more follow

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            PrivateProfileError: If inventory is private
            SteamAPIError: On API errors
        """
        steamid = validate_steam_id(steamid)

        with self._errors("get inventory"):
            url = f"{self.community_base_url}/inventory/{steamid}/{app_id}/{context_id}"

            params = {"l": language, "count": str(count)}

            if start_assetid:
                params["start_assetid"] = start_assetid

            try:
                response_data = await self.client.request(
                    "GET", url, params=params, auth_type="none"
                )
            except SteamAPIError as e:
                # Steam answers a private inventory with HTTP 403 and a null body.
                if e.status_code == 403:
                    raise PrivateProfileError(steamid) from None
                raise

            # Check for common error responses
            if "error" in response_data:
                error_msg = response_data["error"]
                if "private" in error_msg.lower():
                    raise PrivateProfileError(steamid)
                elif "not found" in error_msg.lower():
                    raise PlayerNotFoundError(steamid)
                else:
                    raise SteamAPIError(f"Inventory error: {error_msg}")

            return InventoryResponse.model_validate(response_data)

    async def iter_inventory_pages(
        self,
        steamid: SteamIDLike,
        app_id: int,
        context_id: str = "2",
        count: int = INVENTORY_PAGE_SIZE,
        language: str = "english",
    ) -> AsyncIterator[InventoryResponse]:
        """Iterate over every page of a user's inventory.

        Args:
            steamid: Steam ID of the user
            app_id: Steam App ID
            context_id: Inventory context ID (usually "2")
            count: Page size; Steam allows up to 2000
            language: Language for item descriptions

        Yields:
            Inventory pages, one request each

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            PrivateProfileError: If inventory is private
            SteamAPIError: On API errors
        """
        start_assetid: str | None = None
        while True:
            page = await self.get_inventory(
                steamid, app_id, context_id, start_assetid, count, language
            )
            yield page
            if not page.has_more_items or not page.last_assetid:
                return
            if page.last_assetid == start_assetid:
                raise SteamAPIError("Steam returned the same inventory page twice")
            start_assetid = page.last_assetid

    async def get_full_inventory(
        self,
        steamid: SteamIDLike,
        app_id: int,
        context_id: str = "2",
        count: int = INVENTORY_PAGE_SIZE,
        language: str = "english",
    ) -> InventoryResponse:
        """Get a user's whole inventory, merging every page.

        Args:
            steamid: Steam ID of the user
            app_id: Steam App ID
            context_id: Inventory context ID (usually "2")
            count: Page size; Steam allows up to 2000
            language: Language for item descriptions

        Returns:
            One inventory with every asset, each description once, and
            ``more_items`` unset

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            PrivateProfileError: If inventory is private
            SteamAPIError: On API errors
        """
        merged: InventoryResponse | None = None
        seen: set[tuple[str, str]] = set()
        async for page in self.iter_inventory_pages(
            steamid, app_id, context_id, count, language
        ):
            if merged is None:
                merged = page.model_copy(
                    update={"assets": [], "descriptions": [], "asset_properties": []}
                )
            merged.assets.extend(page.assets)
            merged.asset_properties.extend(page.asset_properties)
            for description in page.descriptions:
                key = (description.classid, description.instanceid)
                if key not in seen:
                    seen.add(key)
                    merged.descriptions.append(description)
        assert merged is not None
        return merged.model_copy(update={"more_items": None, "last_assetid": None})
