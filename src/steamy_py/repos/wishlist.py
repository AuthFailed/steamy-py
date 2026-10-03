"""Wishlist endpoints (steam.wishlist)."""

from collections.abc import Mapping
from typing import Any

from ..models.wishlist import (
    Wishlist,
    WishlistItemCountResponse,
    WishlistItemsOnSale,
    WishlistItemsOnSaleResponse,
    WishlistResponse,
    WishlistSortedFiltered,
    WishlistSortedFilteredResponse,
    WishlistUpdateResponse,
)
from ..steamid import SteamIDLike, validate_app_id, validate_steam_id
from .base import BaseAPI
from .store import _data_request, _store_context

_INTERFACE = "IWishlistService"


class WishlistAPI(BaseAPI):
    """Users' wishlists (IWishlistService).

    Reading a user's wishlist needs no credential and sends none. The methods
    about the signed-in user (adding, removing, the apps on sale) need the
    access token and send only it.
    """

    async def get_wishlist(self, steamid: SteamIDLike) -> Wishlist:
        """Get the apps on a user's wishlist.

        Calls IWishlistService/GetWishlist without a credential. Only app
        ids, wishlist ranks and dates come back; look up names and prices
        with the store methods.

        A private wishlist is not an error: Steam answers it with an empty
        response, so it returns an empty ``Wishlist``, the same as an empty
        wishlist does.

        Args:
            steamid: Steam ID of the user (int, str or SteamID)

        Returns:
            The wishlist; ``items`` is empty when the wishlist is empty or
            not public

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            _INTERFACE,
            "GetWishlist",
            "get wishlist",
            {"steamid": validate_steam_id(steamid)},
            model=WishlistResponse,
            auth_type="none",
        )
        return response.response

    async def get_wishlist_item_count(self, steamid: SteamIDLike) -> int:
        """Get the number of apps on a user's wishlist.

        Calls IWishlistService/GetWishlistItemCount without a credential.

        Args:
            steamid: Steam ID of the user (int, str or SteamID)

        Returns:
            The number of apps on the wishlist; 0 when Steam leaves the
            count out

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            _INTERFACE,
            "GetWishlistItemCount",
            "get wishlist item count",
            {"steamid": validate_steam_id(steamid)},
            model=WishlistItemCountResponse,
            auth_type="none",
        )
        return response.response.count

    async def add_to_wishlist(
        self, appid: int, *, navdata: Mapping[str, Any] | None = None
    ) -> int:
        """Adds an app to the signed-in user's wishlist.

        Calls IWishlistService/AddToWishlist (POST) with the access token,
        which identifies the user. The inputs go in the form body: ``appid``
        alone, or everything as one ``input_json`` field when ``navdata`` is
        given.

        Args:
            appid: Steam App ID of the app to add
            navdata: A ``CUserInterface_NavData`` message (where in Steam's
                UI the add came from), sent as given, e.g. ``{"domain":
                "store.steampowered.com", "controller": "app"}``; Steam does
                not document what it does with it

        Returns:
            The number of apps on the wishlist that Steam reports
            (``wishlist_count``); 0 when Steam leaves it out. Unverified:
            whether Steam counts the app when it was already on the
            wishlist.

        Raises:
            InvalidAppIDError: If ``appid`` is invalid
            AuthenticationError: If the client has no access token, or Steam
                rejects it
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors, e.g. a failing ``x-eresult``
        """
        inputs: dict[str, Any] = {"appid": validate_app_id(appid)}
        if navdata is None:
            result = await self._call_service(
                _INTERFACE,
                "AddToWishlist",
                "add to wishlist",
                inputs,
                model=WishlistUpdateResponse,
                http_method="POST",
                auth_type="access_token",
            )
            return result.response.wishlist_count
        inputs["navdata"] = dict(navdata)
        with self._errors("add to wishlist"):
            data = await self._request(
                _INTERFACE,
                "AddToWishlist",
                "v1",
                auth_type="access_token",
                http_method="POST",
                input_json=inputs,
            )
            return WishlistUpdateResponse.model_validate(data).response.wishlist_count

    async def remove_from_wishlist(self, appid: int) -> int:
        """Removes an app from the signed-in user's wishlist.

        Calls IWishlistService/RemoveFromWishlist (POST) with the access
        token, which identifies the user; ``appid`` goes in the form body.

        Args:
            appid: Steam App ID of the app to remove

        Returns:
            The number of apps on the wishlist that Steam reports
            (``wishlist_count``); 0 when Steam leaves it out

        Raises:
            InvalidAppIDError: If ``appid`` is invalid
            AuthenticationError: If the client has no access token, or Steam
                rejects it
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors, e.g. a failing ``x-eresult``
        """
        result = await self._call_service(
            _INTERFACE,
            "RemoveFromWishlist",
            "remove from wishlist",
            {"appid": validate_app_id(appid)},
            model=WishlistUpdateResponse,
            http_method="POST",
            auth_type="access_token",
        )
        return result.response.wishlist_count

    async def get_wishlist_items_on_sale(
        self,
        *,
        language: str = "english",
        country_code: str = "US",
        include_basic_info: bool = True,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_reviews: bool = False,
        include_all_purchase_options: bool = False,
        include_tag_count: int | None = None,
    ) -> WishlistItemsOnSale:
        """Get the apps on the signed-in user's wishlist that are on sale.

        Calls IWishlistService/GetWishlistItemsOnSale (GET) with the access
        token, which identifies the user; the inputs go in one ``input_json``
        parameter. The ``include_*`` options choose the parts of each
        ``store_item`` Steam fills in; when all are off no data request is
        sent. In Steam's proto ``include_best_purchase_option`` defaults to
        true, so a data request also asks for ``best_purchase_option`` (the
        current price and discount).

        Args:
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and sales, e.g. "DE"
            include_basic_info: Short description, publishers, developers
                and franchises (``basic_info``)
            include_assets: Capsule and header image names (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_reviews: Review summaries (``reviews``)
            include_all_purchase_options: Every package and bundle that
                grants the app (``purchase_options``)
            include_tag_count: Return up to this many weighted tags (``tags``)

        Returns:
            The apps on sale, in ``items``, and ``total_items_on_sale``

        Raises:
            AuthenticationError: If the client has no access token, or Steam
                rejects it
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        inputs: dict[str, Any] = {"context": _store_context(language, country_code)}
        data_request = _data_request(
            include_tag_count,
            include_basic_info=include_basic_info,
            include_assets=include_assets,
            include_release=include_release,
            include_platforms=include_platforms,
            include_reviews=include_reviews,
            include_all_purchase_options=include_all_purchase_options,
        )
        if data_request:
            inputs["data_request"] = data_request
        with self._errors("get wishlist items on sale"):
            data = await self._request(
                _INTERFACE,
                "GetWishlistItemsOnSale",
                "v1",
                auth_type="access_token",
                input_json=inputs,
            )
            return WishlistItemsOnSaleResponse.model_validate(data).response

    async def get_wishlist_sorted_filtered(
        self,
        steamid: SteamIDLike,
        *,
        sort_order: int | None = None,
        filters: Mapping[str, Any] | None = None,
        start_index: int | None = None,
        page_size: int | None = None,
        share_token: str | None = None,
        language: str = "english",
        country_code: str = "US",
        include_basic_info: bool = True,
        include_assets: bool = False,
        include_release: bool = False,
        include_platforms: bool = False,
        include_reviews: bool = False,
        include_all_purchase_options: bool = False,
        include_tag_count: int | None = None,
    ) -> WishlistSortedFiltered:
        """Get a user's wishlist sorted and filtered, with store data.

        Calls IWishlistService/GetWishlistSortedFiltered (GET) without a
        credential; the inputs go in one ``input_json`` parameter. Steam
        describes ``start_index`` and ``page_size`` as the range of items it
        fills with store data; other clients rely on every item that passes
        the filters coming back, in order, with ``store_item`` filled only
        in that range (unverified here). The ``include_*`` options choose
        the parts of ``store_item``; when all are off no data request is
        sent. Unverified: that a private wishlist comes back empty, as it
        does from ``get_wishlist``.

        Args:
            steamid: Steam ID of the user (int, str or SteamID)
            sort_order: Order as Steam's wishlist sort enum number; Steam
                does not publish the enum, and None leaves Steam's default
            filters: A ``CWishlistFilters`` message, sent as given, e.g.
                ``{"min_discount_percent": 50, "only_games": True}``; other
                fields include ``macos_only``, ``steamos_linux_only``,
                ``only_software``, ``only_dlc``, ``only_free``,
                ``max_price_in_cents``, ``has_demo``, ``tagids_must_match``,
                ``excluded_content_descriptors``, ``exclude_types`` and
                ``steam_deck_filters``
            start_index: First item (from 0, Steam's default) of the range
                filled with store data
            page_size: Number of items in that range; Steam's default is 100
            share_token: Token of a shared wishlist; Steam says it decides
                which items are visible and the filters in effect
            language: Language of names and descriptions, e.g. "german"
            country_code: Country for prices and availability, e.g. "DE"
            include_basic_info: Short description, publishers, developers
                and franchises (``basic_info``)
            include_assets: Capsule and header image names (``assets``)
            include_release: Release dates (``release``)
            include_platforms: Supported OSes, VR and Steam Deck rating
                (``platforms``)
            include_reviews: Review summaries (``reviews``)
            include_all_purchase_options: Every package and bundle that
                grants the app (``purchase_options``)
            include_tag_count: Return up to this many weighted tags (``tags``)

        Returns:
            The wishlist, in ``items``

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        inputs: dict[str, Any] = {
            "steamid": validate_steam_id(steamid),
            "context": _store_context(language, country_code),
        }
        data_request = _data_request(
            include_tag_count,
            include_basic_info=include_basic_info,
            include_assets=include_assets,
            include_release=include_release,
            include_platforms=include_platforms,
            include_reviews=include_reviews,
            include_all_purchase_options=include_all_purchase_options,
        )
        if data_request:
            inputs["data_request"] = data_request
        optional = {
            "sort_order": sort_order,
            "filters": None if filters is None else dict(filters),
            "start_index": start_index,
            "page_size": page_size,
            "share_token": share_token,
        }
        inputs.update({name: v for name, v in optional.items() if v is not None})
        with self._errors("get wishlist sorted filtered"):
            data = await self._request(
                _INTERFACE,
                "GetWishlistSortedFiltered",
                "v1",
                auth_type="none",
                input_json=inputs,
            )
            return WishlistSortedFilteredResponse.model_validate(data).response
