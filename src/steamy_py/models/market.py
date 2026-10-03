"""Market related data models for Steam API."""

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import Field

from .base import SteamModel, SteamResponse


def _price_to_cents(price: str | None) -> int | None:
    """Convert a formatted price such as ``"$1,234.56"`` or ``"1,23€"`` to cents.

    The currency symbol may sit on either side. A ``,`` or ``.`` followed by
    one or two trailing digits is the decimal separator; any other separator
    groups thousands.
    """
    if not price:
        return None
    number = re.sub(r"[^\d.,]", "", price).strip(".,")
    if not number:
        return None
    match = re.search(r"[.,](\d{1,2})$", number)
    if match:
        whole = re.sub(r"[.,]", "", number[: match.start()])
        number = f"{whole or 0}.{match.group(1)}"
    else:
        number = re.sub(r"[.,]", "", number)
    try:
        return int((Decimal(number) * 100).to_integral_value())
    except InvalidOperation:
        return None


class MarketItem(SteamModel):
    """Steam Community Market item."""

    market_hash_name: str = Field(description="Market hash name for the item")
    market_name: str = Field(description="Display name in market")
    name: str = Field(description="Item name")
    name_color: str | None = Field(default=None, description="Name color hex")
    type: str | None = Field(default=None, description="Item type")
    commodity: bool = Field(default=False, description="Whether item is a commodity")


class PriceInfo(SteamModel):
    """Item price information."""

    lowest_price: str | None = Field(default=None, description="Lowest current price")
    volume: str | None = Field(default=None, description="24h volume")
    median_price: str | None = Field(default=None, description="Median price")

    @property
    def lowest_price_cents(self) -> int | None:
        """Get lowest price in cents (minor currency units)."""
        return _price_to_cents(self.lowest_price)

    @property
    def median_price_cents(self) -> int | None:
        """Get median price in cents (minor currency units)."""
        return _price_to_cents(self.median_price)


class MarketListing(SteamModel):
    """Market listing for an item."""

    listingid: str = Field(description="Unique listing ID")
    price: int = Field(description="Price in cents")
    fee: int = Field(description="Steam fee in cents")
    steamid_lister: str | None = Field(default=None, description="Seller Steam ID")
    item: dict[str, Any] = Field(description="Item details")

    @property
    def total_price(self) -> int:
        """Get total price including fees."""
        return self.price + self.fee

    @property
    def price_dollars(self) -> float:
        """Get price in dollars."""
        return self.price / 100

    @property
    def total_price_dollars(self) -> float:
        """Get total price in dollars."""
        return self.total_price / 100


class MarketHistoryEntry(SteamModel):
    """Market price history entry."""

    date: str = Field(description="Date string")
    price: float = Field(description="Price")
    volume: int = Field(description="Volume sold")

    @property
    def price_cents(self) -> int:
        """Get price in cents (minor currency units)."""
        return int((Decimal(str(self.price)) * 100).to_integral_value())


class MarketSearch(SteamModel):
    """Market search parameters."""

    query: str | None = Field(default=None, description="Search query")
    start: int = Field(default=0, description="Starting index")
    count: int = Field(default=100, description="Number of results")
    sort_column: str = Field(default="popular", description="Sort column")
    sort_dir: str = Field(default="desc", description="Sort direction")
    appid: int | None = Field(default=None, description="Filter by app ID")


class InventoryItem(SteamModel):
    """Steam inventory item."""

    appid: int = Field(description="App ID")
    contextid: str = Field(description="Context ID")
    assetid: str = Field(description="Asset ID")
    classid: str = Field(description="Class ID")
    instanceid: str = Field(description="Instance ID")
    amount: str = Field(description="Item amount")
    pos: int | None = Field(
        default=None, description="Position in inventory (absent from /inventory/)"
    )


class ItemDescription(SteamModel):
    """Item description from inventory."""

    appid: int = Field(description="App ID")
    classid: str = Field(description="Class ID")
    instanceid: str = Field(description="Instance ID")
    icon_url: str = Field(description="Icon URL path")
    icon_url_large: str | None = Field(default=None, description="Large icon URL path")
    icon_drag_url: str | None = Field(default=None, description="Drag icon URL")
    name: str = Field(description="Item name")
    market_hash_name: str | None = Field(default=None, description="Market hash name")
    market_name: str | None = Field(default=None, description="Market name")
    name_color: str | None = Field(default=None, description="Name color")
    background_color: str | None = Field(default=None, description="Background color")
    type: str = Field(description="Item type")
    tradable: int = Field(description="Tradable flag")
    marketable: int = Field(description="Marketable flag")
    commodity: int = Field(description="Commodity flag")
    market_tradable_restriction: int | None = Field(
        default=None, description="Trade restriction days"
    )
    descriptions: list[dict[str, Any]] = Field(
        default_factory=list, description="Item descriptions"
    )
    owner_descriptions: list[dict[str, Any]] = Field(
        default_factory=list, description="Descriptions only the owner sees"
    )
    actions: list[dict[str, Any]] = Field(
        default_factory=list, description="Item actions, e.g. CS2 inspect links"
    )
    owner_actions: list[dict[str, Any]] = Field(
        default_factory=list, description="Actions only the owner sees"
    )
    market_actions: list[dict[str, Any]] = Field(
        default_factory=list, description="Market actions"
    )
    tags: list[dict[str, Any]] = Field(default_factory=list, description="Item tags")
    fraudwarnings: list[str] = Field(default_factory=list, description="Fraud warnings")
    owner: int | None = Field(default=None, description="Owner flag")
    market_marketable_restriction: int | None = Field(
        default=None, description="Market restriction days"
    )
    market_buy_country_restriction: str | None = Field(
        default=None, description="Country restriction for market purchases"
    )
    sealed: int | None = Field(default=None, description="Sealed flag")

    @property
    def is_tradable(self) -> bool:
        """Check if item is tradable."""
        return self.tradable == 1

    @property
    def is_marketable(self) -> bool:
        """Check if item is marketable."""
        return self.marketable == 1

    @property
    def is_commodity(self) -> bool:
        """Check if item is a commodity."""
        return self.commodity == 1

    @property
    def full_icon_url(self) -> str:
        """Get full icon URL."""
        return f"https://community.cloudflare.steamstatic.com/economy/image/{self.icon_url}"

    @property
    def full_large_icon_url(self) -> str | None:
        """Get full large icon URL."""
        if self.icon_url_large:
            return f"https://community.cloudflare.steamstatic.com/economy/image/{self.icon_url_large}"
        return None


# Response wrapper models
class ItemPriceResponse(SteamResponse):
    """Response for item price lookup."""

    success: bool = Field(description="Request success")
    lowest_price: str | None = Field(default=None, description="Lowest price")
    volume: str | None = Field(default=None, description="24h volume")
    median_price: str | None = Field(default=None, description="Median price")

    def to_price_info(self) -> PriceInfo:
        """Convert to PriceInfo model."""
        return PriceInfo(
            lowest_price=self.lowest_price,
            volume=self.volume,
            median_price=self.median_price,
        )


class MarketListingsResponse(SteamResponse):
    """Sell listings of one item (``/market/listings/{appid}/{hash}/render/``)."""

    success: bool = Field(description="Request success")
    start: int = Field(default=0, description="Starting index")
    pagesize: int = Field(default=0, description="Page size")
    total_count: int = Field(default=0, description="Total listings")
    listinginfo: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="Listings keyed by listing ID"
    )
    assets: dict[str, dict[str, dict[str, dict[str, Any]]]] = Field(
        default_factory=dict,
        description="Listed assets keyed by app ID, context ID, then asset ID",
    )
    currency: list[Any] = Field(default_factory=list, description="Currencies")

    @property
    def has_more_results(self) -> bool:
        """Check if there are more results available."""
        return self.start + self.pagesize < self.total_count


class MarketSearchResponse(SteamResponse):
    """Response for a market search (``/market/search/render/``)."""

    success: bool = Field(description="Request success")
    start: int = Field(description="Starting index")
    pagesize: int = Field(description="Page size")
    total_count: int = Field(description="Total results")
    searchdata: dict[str, Any] = Field(description="Search metadata")
    results: list[dict[str, Any]] = Field(
        default_factory=list, description="Listing results"
    )

    @property
    def has_more_results(self) -> bool:
        """Check if there are more results available."""
        return self.start + self.pagesize < self.total_count


class MarketHistoryResponse(SteamResponse):
    """Response for market price history."""

    success: bool = Field(description="Request success")
    price_prefix: str = Field(description="Price currency prefix")
    price_suffix: str = Field(description="Price currency suffix")
    prices: list[list] = Field(description="Price history data")

    def to_history_entries(self) -> list[MarketHistoryEntry]:
        """Convert raw price data to history entries."""
        entries = []
        for price_data in self.prices:
            if len(price_data) >= 3:
                entries.append(
                    MarketHistoryEntry(
                        date=price_data[0],
                        price=float(price_data[1]),
                        volume=int(price_data[2]),
                    )
                )
        return entries


class InventoryResponse(SteamResponse):
    """Response for Steam inventory."""

    assets: list[InventoryItem] = Field(
        default_factory=list, description="Inventory items"
    )
    descriptions: list[ItemDescription] = Field(
        default_factory=list, description="Item descriptions"
    )
    more_items: int | None = Field(default=None, description="More items flag")
    last_assetid: str | None = Field(
        default=None, description="Last asset ID for pagination"
    )
    total_inventory_count: int | None = Field(
        default=None, description="Total inventory count"
    )
    asset_properties: list[dict[str, Any]] = Field(
        default_factory=list, description="Per-asset properties"
    )
    success: int = Field(description="Success flag")
    rwgrsn: int | None = Field(default=None, description="Request reason code")

    @property
    def is_success(self) -> bool:
        """Check if request was successful."""
        return self.success == 1

    @property
    def has_more_items(self) -> bool:
        """Check if there are more items to load."""
        return self.more_items == 1 if self.more_items is not None else False
