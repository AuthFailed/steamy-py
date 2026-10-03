"""Models for IWishlistService responses.

Steam service methods serialize protobuf messages to JSON and can leave out
fields at their default value (0 or an empty list), so every field here has
a default.
"""

from pydantic import Field

from .base import SteamModel


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
