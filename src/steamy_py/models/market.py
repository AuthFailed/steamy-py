"""Market related data models for Steam API."""

from typing import Any, List

from pydantic import Field

from .base import SteamModel, SteamResponse


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
        """Get lowest price in cents."""
        if self.lowest_price:
            # Parse price string like "$1.23" -> 123
            price_str = self.lowest_price.replace("$", "").replace(",", "")
            try:
                return int(float(price_str) * 100)
            except ValueError:
                return None
        return None

    @property
    def median_price_cents(self) -> int | None:
        """Get median price in cents."""
        if self.median_price:
            price_str = self.median_price.replace("$", "").replace(",", "")
            try:
                return int(float(price_str) * 100)
            except ValueError:
                return None
        return None


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
        """Get price in cents."""
        return int(self.price * 100)


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
    pos: int = Field(description="Position in inventory")


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
    descriptions: list[dict[str, str]] = Field(
        default_factory=list, description="Item descriptions"
    )
    tags: list[dict[str, Any]] = Field(default_factory=list, description="Item tags")

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
    """Response for market listings."""

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
    prices: list[List] = Field(description="Price history data")

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
