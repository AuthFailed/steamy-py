"""Models for IWishlistService responses.

Steam service methods serialize protobuf messages to JSON and can leave out
fields at their default value (0 or an empty list), so every field here has
a default.
"""

from pydantic import Field

from .base import SteamModel
from .store import StoreItem


class WishlistItem(SteamModel):
    """An app on a user's wishlist (``CWishlist_GetWishlist_Response_WishlistItem``)."""

    appid: int = Field(0, description="Steam app ID")
    priority: int = Field(
        0,
        description=(
            "Rank of the app in the user's wishlist order (from 1, possibly "
            "with gaps); 0 when the app has no rank"
        ),
    )
    date_added: int = Field(
        0, description="When the app was added to the wishlist (Unix timestamp)"
    )


class Wishlist(SteamModel):
    """A user's wishlist (``CWishlist_GetWishlist_Response``)."""

    items: list[WishlistItem] = Field(default_factory=list)


class WishlistResponse(SteamModel):
    """Response of GetWishlist."""

    response: Wishlist = Field(default_factory=Wishlist)


class WishlistItemCount(SteamModel):
    """``CWishlist_GetWishlistItemCount_Response``."""

    count: int = Field(0, description="Number of apps on the wishlist")


class WishlistItemCountResponse(SteamModel):
    """Response of GetWishlistItemCount."""

    response: WishlistItemCount = Field(default_factory=WishlistItemCount)


# -- AddToWishlist / RemoveFromWishlist ----------------------------------------------


class WishlistUpdate(SteamModel):
    """``CWishlist_AddToWishlist_Response`` and
    ``CWishlist_RemoveFromWishlist_Response`` (the same single field)."""

    wishlist_count: int = Field(
        0, description="Number of apps on the wishlist, as Steam reports it"
    )


class WishlistUpdateResponse(SteamModel):
    """Response of AddToWishlist and RemoveFromWishlist."""

    response: WishlistUpdate = Field(default_factory=WishlistUpdate)


# -- GetWishlistItemsOnSale ----------------------------------------------------------


class WishlistSaleItem(SteamModel):
    """An app on sale from the signed-in user's wishlist
    (``CWishlist_GetWishlistItemsOnSale_Response_WishlistItem``)."""

    appid: int = Field(0, description="Steam app ID")
    store_item: StoreItem = Field(
        default_factory=StoreItem,
        description="Store data for the app, filled as the data request asked",
    )


class WishlistItemsOnSale(SteamModel):
    """``CWishlist_GetWishlistItemsOnSale_Response``."""

    items: list[WishlistSaleItem] = Field(default_factory=list)
    total_items_on_sale: int = Field(0, description="Number of wishlisted apps on sale")


class WishlistItemsOnSaleResponse(SteamModel):
    """Response of GetWishlistItemsOnSale."""

    response: WishlistItemsOnSale = Field(default_factory=WishlistItemsOnSale)


# -- GetWishlistSortedFiltered -------------------------------------------------------


class WishlistSortedItem(WishlistItem):
    """An app on a sorted and filtered wishlist
    (``CWishlist_GetWishlistSortedFiltered_Response_WishlistItem``)."""

    store_item: StoreItem = Field(
        default_factory=StoreItem,
        description=(
            "Store data for the app; filled only for the items in the "
            "requested range, and only when store data was asked for"
        ),
    )
    category_ids: list[str] = Field(
        default_factory=list,
        description="The user's wishlist categories holding the app (64-bit ids)",
    )


class WishlistSortedFiltered(SteamModel):
    """``CWishlist_GetWishlistSortedFiltered_Response``."""

    items: list[WishlistSortedItem] = Field(default_factory=list)


class WishlistSortedFilteredResponse(SteamModel):
    """Response of GetWishlistSortedFiltered."""

    response: WishlistSortedFiltered = Field(default_factory=WishlistSortedFiltered)
