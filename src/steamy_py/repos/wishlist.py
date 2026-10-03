"""Wishlist endpoints (steam.wishlist)."""

from ..models.wishlist import Wishlist, WishlistItemCountResponse, WishlistResponse
from ..steamid import SteamIDLike, validate_steam_id
from .base import BaseAPI

_INTERFACE = "IWishlistService"


class WishlistAPI(BaseAPI):
    """Users' wishlists (IWishlistService).

    These methods need no credential and never send one.
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
