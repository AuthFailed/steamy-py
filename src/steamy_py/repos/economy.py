"""Economy endpoints (steam.economy): inventories, items and trades.

The community inventory endpoint (``get_inventory`` and friends) is an
unofficial steamcommunity.com page, not part of the Web API: it needs no
credential and is rate limited much more strictly. The other methods call
IEconService; its trade methods answer about the account whose API key or
access token is sent.
"""

import logging
import re
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Any

from ..exceptions import (
    PlayerNotFoundError,
    PrivateProfileError,
    SteamAPIError,
)
from ..models.economy import (
    AssetClassInfo,
    AssetClassInfoResponse,
    EconInventory,
    EconInventoryResponse,
    TradeHistory,
    TradeHistoryResponse,
    TradeHoldDurations,
    TradeHoldDurationsResponse,
    TradeOfferDetails,
    TradeOfferDetailsResponse,
    TradeOffers,
    TradeOffersResponse,
    TradeOffersSummary,
    TradeOffersSummaryResponse,
)
from ..models.market import InventoryResponse
from ..steamid import SteamIDLike, validate_app_id, validate_steam_id
from .base import BaseAPI

logger = logging.getLogger(__name__)

# Largest page Steam serves from /inventory/.
INVENTORY_PAGE_SIZE = 2000

_SERVICE = "IEconService"

# 64-bit ids (class, instance, context, asset, trade offer and trade ids):
# pass them as int or as the decimal string Steam returns.
EconID = int | str

# An item class: its class id, or a (classid, instanceid) tuple for one
# instance of it (instance id None: left to Steam).
AssetClass = EconID | tuple[EconID, EconID | None]

# count is an int32 in CEcon_GetInventoryItemsWithDescriptions_Request.
_INT32_MAX = 2**31 - 1

_UINT64_MAX = 2**64 - 1
_DIGITS_RE = re.compile(r"[0-9]{1,20}", re.ASCII)


def _uint64(value: object, what: str, *, allow_zero: bool = False) -> int:
    """Check a 64-bit id (an int, or its decimal string; not a ``bool``) and
    return it as an int; 0 is accepted only with ``allow_zero``."""
    number = value
    if isinstance(value, str) and _DIGITS_RE.fullmatch(value):
        number = int(value)
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not (0 if allow_zero else 1) <= number <= _UINT64_MAX
    ):
        raise ValueError(f"Invalid {what}: {value!r}")
    return int(number)


def _asset_classes(
    classids: AssetClass | Iterable[AssetClass],
) -> list[dict[str, int]]:
    """``CEconItem_ClassIdentifiers`` for one class id or several.

    Each entry is a class id or a ``(classid, instanceid)`` tuple whose
    instance id may be None. A tuple is always one such pair, also when it
    is passed alone; a str counts as one class id; bytes are rejected rather
    than read as a sequence of ints, and a mapping rather than read as its
    keys.
    """
    if isinstance(classids, Mapping):
        raise ValueError(
            "Expected class ids or (classid, instanceid) tuples, got a mapping"
        )
    if isinstance(classids, int | str | bytes | tuple) or not isinstance(
        classids, Iterable
    ):
        entries: list[Any] = [classids]
    else:
        entries = list(classids)
    classes: list[dict[str, int]] = []
    for entry in entries:
        if not isinstance(entry, tuple):
            entry = (entry, None)
        if len(entry) != 2:
            raise ValueError(f"Expected (classid, instanceid), got {entry!r}")
        classid, instanceid = entry
        identifiers = {"classid": _uint64(classid, "class id")}
        if instanceid is not None:
            identifiers["instanceid"] = _uint64(
                instanceid, "instance id", allow_zero=True
            )
        classes.append(identifiers)
    if not classes:
        raise ValueError("At least one class id must be provided")
    return classes


class EconomyAPI(BaseAPI):
    """Inventories, item descriptions and trade offers."""

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

    # -- IEconService ---------------------------------------------------------

    async def get_asset_class_info(
        self,
        appid: int,
        classids: AssetClass | Iterable[AssetClass],
        language: str | None = None,
    ) -> AssetClassInfo:
        """Get the descriptions of item classes (IEconService/GetAssetClassInfo).

        Sends the API key if the client has one, else the access token.
        Whether Steam needs either is unverified: Steam's own web client
        declares this method with the same flags as store methods that need
        no credential.

        Args:
            appid: App the items belong to
            classids: One class id or several; give a ``(classid,
                instanceid)`` tuple for one instance of a class, alone or in
                a list. A tuple is always such a pair: pass several class
                ids as a list. Ids are ints or decimal strings.
            language: Language of names and descriptions, e.g. "german";
                left to Steam when None

        Returns:
            The descriptions, in ``descriptions``; match them to the classes
            asked for by ``classid`` and ``instanceid``

        Raises:
            InvalidAppIDError: If ``appid`` is invalid
            ValueError: If no class id is given or an id is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        inputs: dict[str, Any] = {
            "appid": validate_app_id(appid),
            "classes": _asset_classes(classids),
        }
        if language is not None:
            inputs["language"] = language
        with self._errors("get asset class info"):
            data = await self._request(
                _SERVICE,
                "GetAssetClassInfo",
                "v1",
                auth_type="any",
                input_json=inputs,
            )
            return AssetClassInfoResponse.model_validate(data).response

    async def get_inventory_items_with_descriptions(
        self,
        steamid: SteamIDLike,
        appid: int,
        contextid: EconID,
        *,
        get_descriptions: bool = True,
        for_trade_offer_verification: bool = False,
        language: str = "english",
        filters: Mapping[str, Any] | None = None,
        start_assetid: EconID | None = None,
        count: int | None = None,
        get_asset_properties: bool = False,
    ) -> EconInventory:
        """Get one page of an inventory with its item descriptions
        (IEconService/GetInventoryItemsWithDescriptions).

        Sends the access token, never the API key. Published clients call
        it for the token owner's own inventory; whether Steam answers for
        other users' inventories is unverified. Page with ``start_assetid``
        while ``more_items`` is set.

        Args:
            steamid: Steam ID of the inventory's owner (int, str or SteamID)
            appid: App the inventory belongs to, e.g. 730
            contextid: Inventory context, e.g. 2 (int or decimal string)
            get_descriptions: Return the item descriptions (``descriptions``)
            for_trade_offer_verification: Ask for the inventory as a trade
                offer would see it (exact effect unverified)
            language: Language of names and descriptions, e.g. "german"
            filters: A ``CEcon_GetInventoryItemsWithDescriptions_Request_
                FilterOptions`` message, sent as given, e.g.
                ``{"tradable_only": True, "assetids": [46153215277]}``
            start_assetid: Return items after this asset id (a previous
                page's ``last_assetid``)
            count: Maximum items to return
            get_asset_properties: Return per-asset properties such as CS2
                wear and pattern (``asset_properties``)

        Returns:
            The page: ``assets``, ``descriptions``, ``asset_properties``,
            ``more_items``, ``last_assetid`` and ``total_inventory_count``

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            InvalidAppIDError: If ``appid`` is invalid
            ValueError: If ``contextid``, ``start_assetid`` or ``count`` is
                invalid
            AuthenticationError: If the client has no access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        if count is not None and (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 1 <= count <= _INT32_MAX
        ):
            raise ValueError(f"Invalid count: {count!r}")
        inputs: dict[str, Any] = {
            "steamid": int(validate_steam_id(steamid)),
            "appid": validate_app_id(appid),
            "contextid": _uint64(contextid, "context id"),
            "get_descriptions": get_descriptions,
            "for_trade_offer_verification": for_trade_offer_verification,
            "language": language,
            "get_asset_properties": get_asset_properties,
        }
        if filters is not None:
            inputs["filters"] = dict(filters)
        if start_assetid is not None:
            inputs["start_assetid"] = _uint64(start_assetid, "asset id")
        if count is not None:
            inputs["count"] = count
        with self._errors("get inventory items with descriptions"):
            data = await self._request(
                _SERVICE,
                "GetInventoryItemsWithDescriptions",
                "v1",
                auth_type="access_token",
                input_json=inputs,
            )
            return EconInventoryResponse.model_validate(data).response

    async def get_trade_offers(
        self,
        *,
        get_sent_offers: bool = True,
        get_received_offers: bool = True,
        get_descriptions: bool = False,
        language: str = "english",
        active_only: bool = True,
        historical_only: bool = False,
        time_historical_cutoff: int | None = None,
        cursor: int | None = None,
    ) -> TradeOffers:
        """Get the account's trade offers (IEconService/GetTradeOffers).

        Sends the API key if the client has one, else the access token; the
        offers are those of the account the credential belongs to. Pass
        the response's ``next_cursor`` back as ``cursor`` for the next page
        while it is not 0.

        Args:
            get_sent_offers: Return offers the account sent
            get_received_offers: Return offers the account received
            get_descriptions: Also return the descriptions of the offers'
                items; Steam fails the request if one cannot be loaded
            language: Language of the descriptions
            active_only: Only offers that are still active, plus offers
                changed since ``time_historical_cutoff``
            historical_only: Only offers that are no longer active
            time_historical_cutoff: Unix timestamp; see ``active_only`` and
                ``historical_only``
            cursor: A previous page's ``next_cursor``

        Returns:
            One page: ``trade_offers_sent``, ``trade_offers_received``,
            ``descriptions`` and ``next_cursor``

        Raises:
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        result = await self._call_service(
            _SERVICE,
            "GetTradeOffers",
            "get trade offers",
            {
                "get_sent_offers": get_sent_offers,
                "get_received_offers": get_received_offers,
                "get_descriptions": get_descriptions,
                "language": language,
                "active_only": active_only,
                "historical_only": historical_only,
                "time_historical_cutoff": time_historical_cutoff,
                "cursor": cursor,
            },
            model=TradeOffersResponse,
            auth_type="any",
        )
        return result.response

    async def get_trade_offer(
        self,
        tradeofferid: EconID,
        *,
        language: str = "english",
        get_descriptions: bool = False,
    ) -> TradeOfferDetails:
        """Get one of the account's trade offers (IEconService/GetTradeOffer).

        Sends the API key if the client has one, else the access token.

        Args:
            tradeofferid: Trade offer id (int or decimal string)
            language: Language of the descriptions
            get_descriptions: Also return the descriptions of the offer's
                items; Steam fails the request if one cannot be loaded

        Returns:
            The offer, in ``offer``, and the descriptions, in
            ``descriptions``

        Raises:
            ValueError: If the trade offer id is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        result = await self._call_service(
            _SERVICE,
            "GetTradeOffer",
            "get trade offer",
            {
                "tradeofferid": _uint64(tradeofferid, "trade offer id"),
                "language": language,
                "get_descriptions": get_descriptions,
            },
            model=TradeOfferDetailsResponse,
            auth_type="any",
        )
        return result.response

    async def get_trade_offers_summary(
        self, time_last_visit: int | None = None
    ) -> TradeOffersSummary:
        """Get counts of the account's pending and new trade offers
        (IEconService/GetTradeOffersSummary).

        Sends the API key if the client has one, else the access token.

        Args:
            time_last_visit: Unix timestamp that "new" and "updated" counts
                are measured from; when None, Steam uses the account's last
                visit to its trade offers page

        Returns:
            The counts

        Raises:
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        result = await self._call_service(
            _SERVICE,
            "GetTradeOffersSummary",
            "get trade offers summary",
            {"time_last_visit": time_last_visit},
            model=TradeOffersSummaryResponse,
            auth_type="any",
        )
        return result.response

    async def get_trade_history(
        self,
        *,
        max_trades: int = 100,
        start_after_time: int | None = None,
        start_after_tradeid: EconID | None = None,
        navigating_back: bool = False,
        get_descriptions: bool = False,
        language: str = "english",
        include_failed: bool = False,
        include_total: bool = False,
    ) -> TradeHistory:
        """Get the account's past trades (IEconService/GetTradeHistory).

        Sends the API key if the client has one, else the access token.
        For the next page pass the last trade's ``time_init`` and
        ``tradeid`` as ``start_after_time`` and ``start_after_tradeid``
        while ``more`` is set.

        Args:
            max_trades: Number of trades to return
            start_after_time: ``time_init`` of the last trade of the
                previous page (of the first, with ``navigating_back``)
            start_after_tradeid: ``tradeid`` of that trade
            navigating_back: Return the trades before the given one instead
            get_descriptions: Also return the descriptions of the traded
                items
            language: Language of the descriptions
            include_failed: Also return failed trades
            include_total: Also return the account's number of trades
                (``total_trades``)

        Returns:
            One page: ``trades``, ``more``, ``total_trades`` and
            ``descriptions``

        Raises:
            ValueError: If ``start_after_tradeid`` is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        if start_after_tradeid is not None:
            start_after_tradeid = _uint64(start_after_tradeid, "trade id")
        result = await self._call_service(
            _SERVICE,
            "GetTradeHistory",
            "get trade history",
            {
                "max_trades": max_trades,
                "start_after_time": start_after_time,
                "start_after_tradeid": start_after_tradeid,
                "navigating_back": navigating_back,
                "get_descriptions": get_descriptions,
                "language": language,
                "include_failed": include_failed,
                "include_total": include_total,
            },
            model=TradeHistoryResponse,
            auth_type="any",
        )
        return result.response

    async def get_trade_status(
        self,
        tradeid: EconID,
        *,
        get_descriptions: bool = False,
        language: str = "english",
    ) -> TradeHistory:
        """Get the status of one of the account's trades
        (IEconService/GetTradeStatus).

        Sends the API key if the client has one, else the access token.
        Steam answers with the trade history message holding just this
        trade.

        Args:
            tradeid: Trade id, e.g. an accepted offer's ``tradeid`` (int or
                decimal string)
            get_descriptions: Also return the descriptions of the traded
                items
            language: Language of the descriptions

        Returns:
            The trade, in ``trades``, and the descriptions, in
            ``descriptions``

        Raises:
            ValueError: If the trade id is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        result = await self._call_service(
            _SERVICE,
            "GetTradeStatus",
            "get trade status",
            {
                "tradeid": _uint64(tradeid, "trade id"),
                "get_descriptions": get_descriptions,
                "language": language,
            },
            model=TradeHistoryResponse,
            auth_type="any",
        )
        return result.response

    async def get_trade_hold_durations(
        self,
        steamid_target: SteamIDLike,
        trade_offer_access_token: str | None = None,
    ) -> TradeHoldDurations:
        """Get how long a trade with a user would be held
        (IEconService/GetTradeHoldDurations).

        Sends the API key if the client has one, else the access token; the
        holds are for a trade between that account and ``steamid_target``.

        Args:
            steamid_target: Steam ID of the trade partner (int, str or
                SteamID)
            trade_offer_access_token: The ``token`` of the partner's trade
                offer URL, needed when the partner is not a friend

        Returns:
            The holds: ``my_escrow``, ``their_escrow`` and ``both_escrow``

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        result = await self._call_service(
            _SERVICE,
            "GetTradeHoldDurations",
            "get trade hold durations",
            {
                "steamid_target": validate_steam_id(steamid_target),
                "trade_offer_access_token": trade_offer_access_token,
            },
            model=TradeHoldDurationsResponse,
            auth_type="any",
        )
        return result.response
