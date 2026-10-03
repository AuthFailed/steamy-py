"""Models for IEconService responses: items, inventories, trade offers and
trades.

IEconService methods serialize protobuf messages (SteamDatabase
``webui/service_econ.proto``) to JSON and may leave out any field at its
default value, so every field here has a default. 64-bit ids (asset, class,
instance, context, trade offer and trade ids, Steam IDs) arrive as strings and
are kept as strings; 64-bit amounts arrive as strings too and are read as
``int``. Proto enums are kept as ``int`` so unknown values still parse.

Item descriptions here follow ``CEconItem_Description``: ``tradable``,
``marketable``, ``commodity`` and ``currency`` are booleans. The community
inventory page (``steam.economy.get_inventory``) sends the same data with 0/1
flags and other required fields, so it keeps its own models in
``models.market``.
"""

from __future__ import annotations

from enum import IntEnum

from pydantic import Field

from ..steamid import SteamID
from .base import SteamModel

_ECONOMY_IMAGE_URL = "https://community.cloudflare.steamstatic.com/economy/image/"


class ETradeOfferState(IntEnum):
    """State of a trade offer (``trade_offer_state``); values from SteamKit."""

    INVALID = 1
    ACTIVE = 2
    ACCEPTED = 3
    COUNTERED = 4
    EXPIRED = 5
    CANCELED = 6
    DECLINED = 7
    INVALID_ITEMS = 8
    CREATED_NEEDS_CONFIRMATION = 9
    CANCELED_BY_SECOND_FACTOR = 10
    IN_ESCROW = 11
    REVERTED = 12


class ETradeOfferConfirmationMethod(IntEnum):
    """How a trade offer awaits confirmation (``confirmation_method``);
    values from SteamKit."""

    INVALID = 0
    EMAIL = 1
    MOBILE_APP = 2


# -- items ----------------------------------------------------------------------


class EconAsset(SteamModel):
    """An item in an inventory or a trade offer (``CEcon_Asset``)."""

    appid: int = 0
    contextid: str = Field("", description="Inventory context id (64-bit)")
    assetid: str = Field("", description="Asset id (64-bit)")
    classid: str = Field("", description="Class id (64-bit)")
    instanceid: str = Field("", description="Instance id (64-bit)")
    currencyid: int = Field(0, description="Currency id, for currency items")
    amount: int = Field(0, description="Stack size")
    missing: bool = Field(
        False, description="The item is no longer where the offer expects it"
    )
    est_usd: int = Field(0, description="Steam's estimated value (unverified unit)")


class EconItemDescriptionLine(SteamModel):
    """One line of an item's description text."""

    type: str = Field("", description='"text" or "html"')
    value: str = ""
    color: str = Field("", description="Hex color, without '#'")
    label: str = ""
    name: str = Field("", description="Line id, e.g. 'exterior_wear'")


class EconItemAction(SteamModel):
    """A link shown with an item, e.g. "Inspect in Game..."."""

    link: str = ""
    name: str = ""


class EconItemTag(SteamModel):
    """A tag of an item, e.g. category "Quality", tag "Unusual"."""

    appid: int = 0
    category: str = ""
    internal_name: str = ""
    localized_category_name: str = ""
    localized_tag_name: str = ""
    color: str = Field("", description="Hex color, without '#'")


class EconItemClassIdentifiers(SteamModel):
    classid: str = Field("", description="Class id (64-bit)")
    instanceid: str = Field("", description="Instance id (64-bit)")


class EconItemContainerProperties(SteamModel):
    """What a container (e.g. a case) holds."""

    contained_items: list[EconItemClassIdentifiers] = Field(default_factory=list)
    search_tags: list[EconItemTag] = Field(default_factory=list)


class EconItemDescription(SteamModel):
    """How an item class looks: name, icon, text, tags and market data
    (``CEconItem_Description``).

    Match it to assets by ``classid`` and ``instanceid``.
    """

    appid: int = 0
    classid: str = Field("", description="Class id (64-bit)")
    instanceid: str = Field("", description="Instance id (64-bit)")
    currency: bool = False
    background_color: str = ""
    icon_url: str = Field("", description="Icon path; see full_icon_url")
    icon_url_large: str = ""
    descriptions: list[EconItemDescriptionLine] = Field(default_factory=list)
    tradable: bool = False
    actions: list[EconItemAction] = Field(default_factory=list)
    owner_descriptions: list[EconItemDescriptionLine] = Field(default_factory=list)
    owner_actions: list[EconItemAction] = Field(default_factory=list)
    fraudwarnings: list[str] = Field(default_factory=list)
    name: str = ""
    name_color: str = ""
    type: str = ""
    market_name: str = ""
    market_hash_name: str = Field("", description="Name of the item on the market")
    market_fee: str = ""
    contained_item: EconItemDescription | None = None
    market_actions: list[EconItemAction] = Field(default_factory=list)
    commodity: bool = False
    market_tradable_restriction: int = Field(
        0, description="Days the item cannot be traded after a market purchase"
    )
    market_marketable_restriction: int = Field(
        0, description="Days the item cannot be listed after it is acquired"
    )
    marketable: bool = False
    tags: list[EconItemTag] = Field(default_factory=list)
    item_expiration: str = ""
    market_fee_app: int = 0
    market_buy_country_restriction: str = ""
    market_sell_country_restriction: str = ""
    sealed: bool = False
    container_properties: EconItemContainerProperties = Field(
        default_factory=EconItemContainerProperties
    )
    market_bucket_group_name: str = ""
    market_bucket_group_id: str = ""
    sealed_type: int = 0
    market_name_inside_group: str = ""
    market_bucket_id: str = ""

    @property
    def full_icon_url(self) -> str | None:
        """The icon's full URL, or None without an icon."""
        return _ECONOMY_IMAGE_URL + self.icon_url if self.icon_url else None

    @property
    def full_large_icon_url(self) -> str | None:
        """The large icon's full URL, or None without one."""
        if self.icon_url_large:
            return _ECONOMY_IMAGE_URL + self.icon_url_large
        return None


class EconAssetProperty(SteamModel):
    """A per-asset value, e.g. a CS2 item's wear (``propertyid`` 2) or
    pattern (``propertyid`` 1); which one is set depends on the property."""

    propertyid: int = 0
    int_value: int = 0
    float_value: float = Field(0.0, description="Sent as a decimal string")
    string_value: str = ""


class EconAssetAccessory(SteamModel):
    """An item attached to an asset (e.g. a sticker or charm)."""

    classid: str = Field("", description="Class id (64-bit)")
    instanceid: str = Field("", description="Instance id (64-bit)")
    standalone_properties: list[EconAssetProperty] = Field(default_factory=list)
    parent_relationship_properties: list[EconAssetProperty] = Field(
        default_factory=list
    )
    nested_accessories: list[EconAssetAccessory] = Field(default_factory=list)


class EconAssetProperties(SteamModel):
    """The properties of one asset (``CEconItem_AssetProperties``)."""

    appid: int = 0
    contextid: str = Field("", description="Inventory context id (64-bit)")
    assetid: str = Field("", description="Asset id (64-bit)")
    asset_properties: list[EconAssetProperty] = Field(default_factory=list)
    asset_accessories: list[EconAssetAccessory] = Field(default_factory=list)


class AssetClassInfo(SteamModel):
    descriptions: list[EconItemDescription] = Field(default_factory=list)


class AssetClassInfoResponse(SteamModel):
    """IEconService/GetAssetClassInfo."""

    response: AssetClassInfo = Field(default_factory=AssetClassInfo)


class EconInventory(SteamModel):
    """One page of an inventory (IEconService/GetInventoryItemsWithDescriptions)."""

    assets: list[EconAsset] = Field(default_factory=list)
    descriptions: list[EconItemDescription] = Field(default_factory=list)
    missing_assets: list[EconAsset] = Field(default_factory=list)
    more_items: bool = Field(False, description="Whether another page follows")
    last_assetid: str = Field(
        "", description="Pass as start_assetid to get the next page"
    )
    total_inventory_count: int = 0
    asset_properties: list[EconAssetProperties] = Field(default_factory=list)


class EconInventoryResponse(SteamModel):
    """IEconService/GetInventoryItemsWithDescriptions."""

    response: EconInventory = Field(default_factory=EconInventory)


# -- trade offers -----------------------------------------------------------------


class TradeOffer(SteamModel):
    """A trade offer (``CEcon_TradeOffer``), seen from the requesting
    account: ``items_to_give`` are its items, ``items_to_receive`` the
    partner's."""

    tradeofferid: str = Field("", description="Trade offer id (64-bit)")
    accountid_other: int = Field(0, description="32-bit account id of the partner")
    message: str = ""
    expiration_time: int = Field(0, description="Unix timestamp")
    trade_offer_state: int = Field(0, description="ETradeOfferState")
    items_to_give: list[EconAsset] = Field(default_factory=list)
    items_to_receive: list[EconAsset] = Field(default_factory=list)
    is_our_offer: bool = Field(False, description="The requesting account sent it")
    time_created: int = Field(0, description="Unix timestamp")
    time_updated: int = Field(0, description="Unix timestamp")
    tradeid: str = Field(
        "", description="Id of the trade (64-bit), once the offer is accepted"
    )
    from_real_time_trade: bool = False
    escrow_end_date: int = Field(
        0, description="Unix timestamp the trade hold ends; 0 without a hold"
    )
    confirmation_method: int = Field(0, description="ETradeOfferConfirmationMethod")
    partner_confirmation_method: int = Field(
        0, description="ETradeOfferConfirmationMethod"
    )
    eresult: int = Field(1, description="EResult")
    delay_settlement: bool = False
    settlement_date: int = Field(0, description="Unix timestamp")

    @property
    def steamid_other(self) -> SteamID | None:
        """The partner's Steam ID, or None if ``accountid_other`` is unset."""
        if not self.accountid_other:
            return None
        return SteamID.from_account_id(self.accountid_other)


class TradeOffers(SteamModel):
    """IEconService/GetTradeOffers: one page of trade offers."""

    trade_offers_sent: list[TradeOffer] = Field(default_factory=list)
    trade_offers_received: list[TradeOffer] = Field(default_factory=list)
    descriptions: list[EconItemDescription] = Field(default_factory=list)
    next_cursor: int = Field(0, description="Cursor of the next page; 0 at the end")


class TradeOffersResponse(SteamModel):
    response: TradeOffers = Field(default_factory=TradeOffers)


class TradeOfferDetails(SteamModel):
    """IEconService/GetTradeOffer: one offer and, if asked for, the
    descriptions of its items."""

    offer: TradeOffer = Field(default_factory=TradeOffer)
    descriptions: list[EconItemDescription] = Field(default_factory=list)


class TradeOfferDetailsResponse(SteamModel):
    response: TradeOfferDetails = Field(default_factory=TradeOfferDetails)


class TradeOffersSummary(SteamModel):
    """IEconService/GetTradeOffersSummary: counts of trade offers."""

    pending_received_count: int = 0
    new_received_count: int = 0
    updated_received_count: int = 0
    historical_received_count: int = 0
    pending_sent_count: int = 0
    newly_accepted_sent_count: int = 0
    updated_sent_count: int = 0
    historical_sent_count: int = 0
    escrow_received_count: int = 0
    escrow_sent_count: int = 0
    provisional: int = 0


class TradeOffersSummaryResponse(SteamModel):
    response: TradeOffersSummary = Field(default_factory=TradeOffersSummary)


# -- trades -------------------------------------------------------------------------


class TradedAsset(SteamModel):
    """An item that changed hands in a trade; ``new_*`` locate it in the
    receiving inventory."""

    appid: int = 0
    contextid: str = Field("", description="Context id before the trade (64-bit)")
    assetid: str = Field("", description="Asset id before the trade (64-bit)")
    amount: int = 0
    classid: str = Field("", description="Class id (64-bit)")
    instanceid: str = Field("", description="Instance id (64-bit)")
    new_assetid: str = Field("", description="Asset id after the trade (64-bit)")
    new_contextid: str = Field("", description="Context id after the trade (64-bit)")
    rollback_new_assetid: str = ""
    rollback_new_contextid: str = ""


class TradedCurrency(SteamModel):
    """A currency amount that changed hands in a trade."""

    appid: int = 0
    contextid: str = Field("", description="Context id (64-bit)")
    currencyid: int = 0
    amount: int = 0
    fee_amount: int = 0
    classid: str = Field("", description="Class id (64-bit)")
    new_currencyid: int = 0
    new_contextid: str = ""
    rollback_new_currencyid: int = 0
    rollback_new_contextid: str = ""


class TradeAuthorization(SteamModel):
    """How a trade was confirmed."""

    is_sender: bool = False
    confirm_type: int = 0
    time_confirmed: int = Field(0, description="Unix timestamp")
    country: str = ""
    state: str = ""
    city: str = ""
    token_id: str = Field("", description="Id of the confirming device (64-bit)")


class TradeDevice(SteamModel):
    """A device that confirmed trades (``devices`` of the trade history)."""

    token_id: str = Field("", description="Device id (64-bit)")
    first_authed: int = Field(0, description="Unix timestamp")
    current_device: bool = False
    platform_type: int = 0
    guard_type: int = 0
    authentication_type: int = 0


class Trade(SteamModel):
    """A completed, pending or failed trade (``trades`` of the trade history)."""

    tradeid: str = Field("", description="Trade id (64-bit)")
    steamid_other: str = Field("", description="Steam ID of the partner")
    time_init: int = Field(0, description="Unix timestamp the trade started")
    time_escrow_end: int = Field(0, description="Unix timestamp the hold ends")
    status: int = Field(0, description="Trade status (ETradeStatus)")
    assets_received: list[TradedAsset] = Field(default_factory=list)
    assets_given: list[TradedAsset] = Field(default_factory=list)
    currency_received: list[TradedCurrency] = Field(default_factory=list)
    currency_given: list[TradedCurrency] = Field(default_factory=list)
    time_settlement: int = Field(0, description="Unix timestamp")
    time_mod: int = Field(0, description="Unix timestamp of the last change")
    rollback_trade: str = Field(
        "", description="Id of the trade that rolled this one back (64-bit)"
    )
    trade_auth: TradeAuthorization = Field(default_factory=TradeAuthorization)


class TradeHistory(SteamModel):
    """IEconService/GetTradeHistory, and GetTradeStatus (the same message)."""

    total_trades: int = Field(0, description="Set when include_total was asked for")
    more: bool = Field(False, description="Whether more trades follow")
    trades: list[Trade] = Field(default_factory=list)
    descriptions: list[EconItemDescription] = Field(default_factory=list)
    devices: list[TradeDevice] = Field(default_factory=list)


class TradeHistoryResponse(SteamModel):
    response: TradeHistory = Field(default_factory=TradeHistory)


class TradeHoldScenario(SteamModel):
    """How long a trade's items would be held."""

    escrow_end_duration_seconds: int = Field(0, description="0 without a hold")
    escrow_end_date: int = Field(0, description="Unix timestamp the hold would end")
    escrow_end_date_rfc3339: str = ""


class TradeHoldDurations(SteamModel):
    """IEconService/GetTradeHoldDurations: holds for the requesting
    account's items (``my_escrow``), the partner's (``their_escrow``) and a
    trade with items from both (``both_escrow``)."""

    my_escrow: TradeHoldScenario = Field(default_factory=TradeHoldScenario)
    their_escrow: TradeHoldScenario = Field(default_factory=TradeHoldScenario)
    both_escrow: TradeHoldScenario = Field(default_factory=TradeHoldScenario)


class TradeHoldDurationsResponse(SteamModel):
    response: TradeHoldDurations = Field(default_factory=TradeHoldDurations)
