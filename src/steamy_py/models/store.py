"""Models for store responses: IStoreBrowseService, IStoreQueryService,
IStoreMarketingService, ISteamChartsService, IStoreTopSellersService,
IStoreService, ICommunityService, and the store.steampowered.com
storesearch, packagedetails and appreviews pages.

Service methods serialize protobuf messages to JSON and leave out every field
at its default value, so every field here has a default. 64-bit ids arrive as
strings and are kept as strings; 64-bit prices arrive as strings too and are
read as ``int``. Proto enums are kept as ``int`` so unknown values still parse;
the ``IntEnum`` classes below give names to the values Steam documents.
"""

from enum import IntEnum
from typing import Any

from pydantic import AliasChoices, Field

from .base import SteamModel


class EStoreItemType(IntEnum):
    """Kind of store item (``StoreItem.item_type``)."""

    INVALID = -1
    APP = 0
    PACKAGE = 1
    BUNDLE = 2
    MTX = 3
    TAG = 4
    CREATOR = 5
    HUB_CATEGORY = 6
    SALE_PAGE = 7


class EStoreAppType(IntEnum):
    """Kind of app (``StoreItem.type``)."""

    GAME = 0
    DEMO = 1
    MOD = 2
    MOVIE = 3
    DLC = 4
    GUIDE = 5
    SOFTWARE = 6
    VIDEO = 7
    SERIES = 8
    EPISODE = 9
    HARDWARE = 10
    MUSIC = 11
    BETA = 12
    TOOL = 13
    ADVERTISING = 14


class EUserReviewScore(IntEnum):
    """Review rating (``StoreReviewSummary.review_score``)."""

    NONE = 0
    OVERWHELMINGLY_NEGATIVE = 1
    VERY_NEGATIVE = 2
    NEGATIVE = 3
    MOSTLY_NEGATIVE = 4
    MIXED = 5
    MOSTLY_POSITIVE = 6
    POSITIVE = 7
    VERY_POSITIVE = 8
    OVERWHELMINGLY_POSITIVE = 9


class ESteamDeckCompatibilityCategory(IntEnum):
    """Steam Deck rating (``StoreItemPlatforms.steam_deck_compat_category``)."""

    UNKNOWN = 0
    UNSUPPORTED = 1
    PLAYABLE = 2
    VERIFIED = 3


# -- IStoreBrowseService/GetItems ----------------------------------------------


class StoreItemID(SteamModel):
    """Identifies a store item; exactly one field is set."""

    appid: int = 0
    packageid: int = 0
    bundleid: int = 0
    tagid: int = 0
    creatorid: int = 0
    hubcategoryid: int = 0
    salepagegid: str = Field("", description="Sale page id (64-bit)")


class StoreItemDemo(SteamModel):
    appid: int = 0
    label: str = ""
    show_above_purchase: bool = False


class StoreItemPlaytest(SteamModel):
    appid: int = 0
    is_open: bool = False


class StoreItemRelatedF2P(SteamModel):
    """A free-to-play version of a paid app."""

    appid: int = 0
    header_text: str = ""
    description_text: str = ""


class StoreItemRelatedItems(SteamModel):
    """Apps related to an item: its parent app, demos and playtests."""

    parent_appid: int = Field(0, description="App this DLC, demo or tool is for")
    demo_appid: list[int] = Field(default_factory=list)
    standalone_demo_appid: list[int] = Field(default_factory=list)
    demos: list[StoreItemDemo] = Field(default_factory=list)
    standalone_demos: list[StoreItemDemo] = Field(default_factory=list)
    playtests: list[StoreItemPlaytest] = Field(default_factory=list)
    related_f2p: StoreItemRelatedF2P = Field(default_factory=StoreItemRelatedF2P)
    dlc_parent_appids: list[int] = Field(default_factory=list)


class StoreItemCategories(SteamModel):
    """Store category ids (e.g. 2 Single-player, 1 Multi-player)."""

    supported_player_categoryids: list[int] = Field(default_factory=list)
    feature_categoryids: list[int] = Field(default_factory=list)
    controller_categoryids: list[int] = Field(default_factory=list)


class StoreReviewSummary(SteamModel):
    review_count: int = 0
    percent_positive: int = 0
    review_score: int = Field(0, description="An EUserReviewScore")
    review_score_label: str = Field("", description='e.g. "Very Positive"')


class StoreItemReviews(SteamModel):
    summary_filtered: StoreReviewSummary = Field(default_factory=StoreReviewSummary)
    summary_unfiltered: StoreReviewSummary = Field(default_factory=StoreReviewSummary)
    summary_language_specific: StoreReviewSummary = Field(
        default_factory=StoreReviewSummary
    )


class StoreItemCreator(SteamModel):
    """A publisher, developer or franchise."""

    name: str = ""
    creator_clan_account_id: int = Field(
        0, description="Account id of the creator's Steam group"
    )


class StoreItemBasicInfo(SteamModel):
    short_description: str = ""
    publishers: list[StoreItemCreator] = Field(default_factory=list)
    developers: list[StoreItemCreator] = Field(default_factory=list)
    franchises: list[StoreItemCreator] = Field(default_factory=list)
    capsule_headline: str = ""


class StoreItemTag(SteamModel):
    tagid: int = 0
    weight: int = 0


class StoreItemAssets(SteamModel):
    """Image file names; put one into ``asset_url_format`` for its path.

    ``asset_url_format`` looks like ``steam/apps/620/${FILENAME}?t=...``,
    relative to the store's asset CDN.
    """

    asset_url_format: str = ""
    main_capsule: str = ""
    small_capsule: str = ""
    header: str = ""
    package_header: str = ""
    page_background: str = ""
    hero_capsule: str = ""
    hero_capsule_2x: str = ""
    library_capsule: str = ""
    library_capsule_2x: str = ""
    library_hero: str = ""
    library_hero_2x: str = ""
    community_icon: str = ""
    clan_avatar: str = ""
    page_background_path: str = ""
    raw_page_background: str = ""
    edition_comparison: str = ""
    main_capsule_2x: str = ""
    small_capsule_2x: str = ""
    header_2x: str = ""
    last_modified: int = 0


class StoreItemReleaseInfo(SteamModel):
    """Release dates (Unix times) and coming-soon state."""

    steam_release_date: int = 0
    original_release_date: int = 0
    original_steam_release_date: int = 0
    is_coming_soon: bool = False
    is_preload: bool = False
    custom_release_date_message: str = ""
    is_abridged_release_date: bool = False
    coming_soon_display: str = ""
    is_early_access: bool = False
    release_from_early_access_date: int = 0
    release_from_early_access_style: int = 0
    mac_release_date: int = 0
    linux_release_date: int = 0
    limited_launch_active: bool = False
    advance_access_date: int = 0


class StoreItemVRSupport(SteamModel):
    vrhmd: bool = False
    vrhmd_only: bool = False
    htc_vive: bool = False
    oculus_rift: bool = False
    windows_mr: bool = False
    valve_index: bool = False


class StoreItemPlatforms(SteamModel):
    windows: bool = False
    mac: bool = False
    steamos_linux: bool = False
    vr_support: StoreItemVRSupport = Field(default_factory=StoreItemVRSupport)
    steam_deck_compat_category: int = Field(
        0, description="An ESteamDeckCompatibilityCategory"
    )
    steam_os_compat_category: int = 0
    steam_frame_compat_category: int = 0
    steam_machine_compat_category: int = 0


class StoreGameRating(SteamModel):
    """Age rating, e.g. ESRB or PEGI."""

    type: str = Field("", description='Rating board, e.g. "esrb", "pegi"')
    rating: str = Field("", description='e.g. "m", "e10"')
    descriptors: list[str] = Field(default_factory=list)
    interactive_elements: str = ""
    agency: int = 0
    banned: bool = False
    esrb_online_music_not_rated: bool = False
    esrb_online_interactions_not_rated: bool = False
    survey_interactive_elements: list[int] = Field(default_factory=list)
    required_age: int = 0
    use_age_gate: bool = False
    descriptor_images: list[int] = Field(default_factory=list)
    image_url: str = ""
    image_target: str = ""


class StoreItemDiscount(SteamModel):
    discount_amount: int = Field(0, description="Discount in cents")
    discount_description: str = ""
    discount_end_date: int = Field(0, description="Unix time the discount ends")
    master_sub_appid: int = 0


class StorePurchaseOption(SteamModel):
    """A package or bundle that grants the item, with its price.

    Prices are in cents of the requested country's currency; the
    ``formatted_*`` fields hold them as displayed (e.g. "$9.99").
    """

    packageid: int = 0
    bundleid: int = 0
    purchase_option_name: str = ""
    final_price_in_cents: int = 0
    original_price_in_cents: int = 0
    formatted_final_price: str = ""
    formatted_original_price: str = ""
    discount_pct: int = 0
    bundle_discount_pct: int = 0
    is_free_to_keep: bool = False
    price_before_bundle_discount: int = 0
    formatted_price_before_bundle_discount: str = ""
    active_discounts: list[StoreItemDiscount] = Field(default_factory=list)
    user_can_purchase_as_gift: bool = False
    is_commercial_license: bool = False
    should_suppress_discount_pct: bool = False
    hide_discount_pct_for_compliance: bool = False
    included_game_count: int = 1
    lowest_recent_price_in_cents: int = 0
    requires_shipping: bool = False
    recurrence_info: dict[str, Any] = Field(
        default_factory=dict, description="Subscription renewal terms"
    )
    free_to_keep_ends: int = 0
    must_purchase_as_set: bool = False
    package_group: str = "default"
    is_edition: bool = False
    free_to_keep_base_package: int = 0
    price_cannot_be_displayed_as_discount: bool = False
    price_to_base_discount_on: int = 0
    free_with_master_sub_appid: int = 0
    formatted_lowest_recent_price: str = ""
    is_free_license: bool = False


class StoreScreenshot(SteamModel):
    filename: str = Field("", description="Path relative to the asset CDN")
    ordinal: int = 0


class StoreItemScreenshots(SteamModel):
    all_ages_screenshots: list[StoreScreenshot] = Field(default_factory=list)
    mature_content_screenshots: list[StoreScreenshot] = Field(default_factory=list)


class StoreItemSupportedLanguage(SteamModel):
    elanguage: int = Field(-1, description="An ELanguage")
    supported: bool = False
    full_audio: bool = False
    subtitles: bool = False
    eadditionallanguage: int = -1


class StoreItemLink(SteamModel):
    link_type: int = Field(0, description="An EStoreLinkType (1 YouTube, ...)")
    url: str = ""
    text: str = ""


class StoreItemFreeWeekend(SteamModel):
    start_time: int = 0
    end_time: int = 0
    text: str = ""
    appid: int = 0


class StoreItem(SteamModel):
    """An app, package, bundle or other store item.

    Which nested parts are filled in depends on the data request: e.g.
    ``basic_info`` needs ``include_basic_info``, ``assets`` needs
    ``include_assets``. Parts that were not requested keep their defaults.
    """

    # Steam's proto declares k_EStoreItemType_Invalid (-1) as the default.
    item_type: int = Field(-1, description="An EStoreItemType")
    id: int = Field(0, description="Id of the item (an app id for apps)")
    success: int = Field(0, description="EResult: 1 when Steam found the item")
    visible: bool = False
    # Steam's own spelling.
    unvailable_for_country_restriction: bool = False
    name: str = ""
    store_url_path: str = Field("", description='e.g. "app/620/Portal_2/"')
    store_url_slug: str = ""
    appid: int = 0
    type: int = Field(0, description="An EStoreAppType")
    included_types: list[int] = Field(default_factory=list)
    included_appids: list[int] = Field(default_factory=list)
    is_free: bool = False
    is_early_access: bool = False
    related_items: StoreItemRelatedItems = Field(default_factory=StoreItemRelatedItems)
    included_items: dict[str, Any] = Field(
        default_factory=dict, description="Apps, packages and bundles inside"
    )
    content_descriptorids: list[int] = Field(default_factory=list)
    tagids: list[int] = Field(default_factory=list)
    categories: StoreItemCategories = Field(default_factory=StoreItemCategories)
    reviews: StoreItemReviews = Field(default_factory=StoreItemReviews)
    basic_info: StoreItemBasicInfo = Field(default_factory=StoreItemBasicInfo)
    tags: list[StoreItemTag] = Field(default_factory=list)
    assets: StoreItemAssets = Field(default_factory=StoreItemAssets)
    release: StoreItemReleaseInfo = Field(default_factory=StoreItemReleaseInfo)
    platforms: StoreItemPlatforms = Field(default_factory=StoreItemPlatforms)
    game_rating: StoreGameRating = Field(default_factory=StoreGameRating)
    is_coming_soon: bool = False
    best_purchase_option: StorePurchaseOption = Field(
        default_factory=StorePurchaseOption
    )
    purchase_options: list[StorePurchaseOption] = Field(default_factory=list)
    accessories: list[StorePurchaseOption] = Field(default_factory=list)
    self_purchase_option: StorePurchaseOption = Field(
        default_factory=StorePurchaseOption
    )
    screenshots: StoreItemScreenshots = Field(default_factory=StoreItemScreenshots)
    trailers: dict[str, Any] = Field(
        default_factory=dict, description="highlights and other_trailers"
    )
    supported_languages: list[StoreItemSupportedLanguage] = Field(default_factory=list)
    store_url_path_override: str = ""
    free_weekend: StoreItemFreeWeekend = Field(default_factory=StoreItemFreeWeekend)
    unlisted: bool = False
    game_count: int = 0
    internal_name: str = ""
    # Field 58 is "full_description" in the webui proto and
    # "full_description_bbcode" in the steamclient one; accept either.
    full_description: str = Field(
        "",
        validation_alias=AliasChoices("full_description", "full_description_bbcode"),
    )
    is_free_temporarily: bool = False
    assets_without_overrides: StoreItemAssets = Field(default_factory=StoreItemAssets)
    user_filter_failure: dict[str, Any] = Field(default_factory=dict)
    links: list[StoreItemLink] = Field(default_factory=list)
    purchase_description_bbcode: str = ""
    package_groups: list[dict[str, Any]] = Field(default_factory=list)
    extra_details: dict[str, Any] = Field(default_factory=dict)
    gid: str = Field("", description="64-bit id")
    optin_registration_tags: list[dict[str, Any]] = Field(default_factory=list)


class StoreItems(SteamModel):
    """Body of IStoreBrowseService/GetItems: one item per requested id."""

    store_items: list[StoreItem] = Field(default_factory=list)


class StoreItemsResponse(SteamModel):
    """Response of IStoreBrowseService/GetItems."""

    response: StoreItems = Field(default_factory=StoreItems)


# -- IStoreQueryService/SearchSuggestions --------------------------------------


class StoreQueryPerResultMetadata(SteamModel):
    id: StoreItemID = Field(default_factory=StoreItemID)
    score: float = 0.0
    spellcheck_generated_result: bool = False


class StoreQueryResultMetadata(SteamModel):
    total_matching_records: int = 0
    start: int = 0
    count: int = 0
    per_result_metadata: list[StoreQueryPerResultMetadata] = Field(default_factory=list)
    spellcheck_suggestions: list[str] = Field(default_factory=list)


class SearchSuggestions(SteamModel):
    """Body of IStoreQueryService/SearchSuggestions.

    ``ids`` lists the matches in order; ``store_items`` holds their data.
    """

    metadata: StoreQueryResultMetadata = Field(default_factory=StoreQueryResultMetadata)
    ids: list[StoreItemID] = Field(default_factory=list)
    store_items: list[StoreItem] = Field(default_factory=list)


class SearchSuggestionsResponse(SteamModel):
    """Response of IStoreQueryService/SearchSuggestions."""

    response: SearchSuggestions = Field(default_factory=SearchSuggestions)


# -- store.steampowered.com/api/storesearch -------------------------------------


class StoreSearchPrice(SteamModel):
    """Price in cents of ``currency``."""

    currency: str = Field("", description='e.g. "USD"')
    initial: int = Field(0, description="Price before discount, in cents")
    final: int = Field(0, description="Price after discount, in cents")


class StoreSearchPlatforms(SteamModel):
    windows: bool = False
    mac: bool = False
    linux: bool = False


class StoreSearchItem(SteamModel):
    """One result of the store search."""

    type: str = Field("", description='e.g. "app"')
    name: str = ""
    id: int = Field(0, description="App id")
    price: StoreSearchPrice | None = Field(
        None, description="None for free apps, which Steam sends without a price"
    )
    tiny_image: str = Field("", description="URL of the 231x87 capsule image")
    metascore: str = Field("", description='Metacritic score, e.g. "95", or ""')
    platforms: StoreSearchPlatforms = Field(default_factory=StoreSearchPlatforms)
    streamingvideo: bool = False
    controller_support: str = Field(
        "", description='"full" or "partial"; "" when Steam does not say'
    )


class StoreSearchResult(SteamModel):
    """Response of store.steampowered.com/api/storesearch."""

    total: int = 0
    items: list[StoreSearchItem] = Field(default_factory=list)


# -- IStoreBrowseService/GetStoreCategories ------------------------------------


class EStoreCategoryType(IntEnum):
    """Kind of store category (``StoreCategory.type``)."""

    CATEGORY = 0
    SUPPORTED_PLAYERS = 1
    FEATURE = 2
    CONTROLLER_SUPPORT = 3
    CLOUD_GAMING = 4


class StoreCategory(SteamModel):
    """A store category, e.g. 2 "Single-player" or 28 "Full controller support".

    The ids are the ones in ``StoreItem.categories``.
    """

    categoryid: int = 0
    type: int = Field(0, description="An EStoreCategoryType")
    internal_name: str = Field("", description='e.g. "Full Controller Support"')
    display_name: str = Field("", description='e.g. "Full controller support"')
    image_url: str = Field(
        "", description='Relative icon path, e.g. "public/images/v6/ico/ico_cards.png"'
    )
    show_in_search: bool = False
    computed: bool = False
    edit_url: str = ""
    edit_sort_order: int = 0


class StoreCategories(SteamModel):
    """Body of IStoreBrowseService/GetStoreCategories."""

    categories: list[StoreCategory] = Field(default_factory=list)


class StoreCategoriesResponse(SteamModel):
    """Response of IStoreBrowseService/GetStoreCategories."""

    response: StoreCategories = Field(default_factory=StoreCategories)


# -- IStoreBrowseService/GetDLCForApps -----------------------------------------


class StoreDLCData(SteamModel):
    """A DLC of one of the requested apps."""

    appid: int = Field(0, description="App id of the DLC")
    parentappid: int = Field(0, description="App the DLC is for")
    release_date: int = Field(0, description="Release date (Unix time)")
    coming_soon: bool = False
    price: int = Field(
        0,
        description=(
            "Price; an int64 Steam sends as a string. Unverified: presumably "
            "in cents of the context country's currency"
        ),
    )
    discount: int = Field(0, description="Discount; unverified: presumably percent")
    free: bool = False


class StoreAppPlaytime(SteamModel):
    """The signed-in user's playtime in one of the requested apps."""

    appid: int = 0
    playtime: int = Field(0, description="Playtime; unverified: presumably minutes")
    last_played: int = Field(0, description="Last played (Unix time)")


class DLCForApps(SteamModel):
    """Body of IStoreBrowseService/GetDLCForApps."""

    dlc_data: list[StoreDLCData] = Field(default_factory=list)
    playtime: list[StoreAppPlaytime] = Field(default_factory=list)


class DLCForAppsResponse(SteamModel):
    """Response of IStoreBrowseService/GetDLCForApps."""

    response: DLCForApps = Field(default_factory=DLCForApps)


# -- IStoreBrowseService/GetDLCForAppsSolr -------------------------------------


class AppDLCList(SteamModel):
    """The DLC of one app."""

    parent_appid: int = Field(0, description="App the DLC is for")
    dlc_appids: list[int] = Field(default_factory=list)


class DLCForAppsSolr(SteamModel):
    """Body of IStoreBrowseService/GetDLCForAppsSolr."""

    dlc_lists: list[AppDLCList] = Field(default_factory=list)


class DLCForAppsSolrResponse(SteamModel):
    """Response of IStoreBrowseService/GetDLCForAppsSolr."""

    response: DLCForAppsSolr = Field(default_factory=DLCForAppsSolr)


# -- ISteamChartsService -------------------------------------------------------


class ConcurrentPlayersRank(SteamModel):
    """A game's place on the chart of games by current players."""

    rank: int = 0
    appid: int = 0
    item: StoreItem = Field(
        default_factory=StoreItem, description="Store data, when requested"
    )
    concurrent_in_game: int = Field(0, description="Players in game now")
    peak_in_game: int = Field(
        0, description="Peak players in game; the period is unverified"
    )


class GamesByConcurrentPlayers(SteamModel):
    """Body of ISteamChartsService/GetGamesByConcurrentPlayers."""

    last_update: int = Field(0, description="When the counts were taken (Unix time)")
    ranks: list[ConcurrentPlayersRank] = Field(default_factory=list)


class GamesByConcurrentPlayersResponse(SteamModel):
    """Response of ISteamChartsService/GetGamesByConcurrentPlayers."""

    response: GamesByConcurrentPlayers = Field(default_factory=GamesByConcurrentPlayers)


class MostPlayedGameRank(SteamModel):
    """A game's place on the most played games chart."""

    rank: int = 0
    appid: int = 0
    item: StoreItem = Field(
        default_factory=StoreItem, description="Store data, when requested"
    )
    last_week_rank: int = Field(0, description="Rank a week before; 0 when not sent")
    peak_in_game: int = Field(0, description="Peak players in game")
    daily_active_players: int = 0


class MostPlayedGames(SteamModel):
    """Body of ISteamChartsService/GetMostPlayedGames."""

    rollup_date: int = Field(0, description="Date of the chart's rollup (Unix time)")
    ranks: list[MostPlayedGameRank] = Field(default_factory=list)


class MostPlayedGamesResponse(SteamModel):
    """Response of ISteamChartsService/GetMostPlayedGames."""

    response: MostPlayedGames = Field(default_factory=MostPlayedGames)


# -- IStoreMarketingService/GetItemsToFeature ----------------------------------


class StoreCapsule(SteamModel):
    """A featured store item: its id, and its data when requested."""

    item_id: StoreItemID = Field(default_factory=StoreItemID)
    item: StoreItem = Field(default_factory=StoreItem)


class StoreSpotlight(SteamModel):
    """A store spotlight: a promoted item with its own title, text and art."""

    item_id: StoreItemID = Field(default_factory=StoreItemID)
    associated_item: StoreItem = Field(default_factory=StoreItem)
    spotlight_template: str = ""
    spotlight_title: str = ""
    spotlight_body: str = ""
    asset_url: str = ""
    spotlight_link_url: str = ""
    start_date: int = Field(0, description="Unix time")
    end_date: int = Field(0, description="Unix time")


class ItemsToFeature(SteamModel):
    """Body of IStoreMarketingService/GetItemsToFeature.

    Each list is filled only when the request asked for it.
    """

    spotlights: list[StoreSpotlight] = Field(default_factory=list)
    daily_deals: list[StoreCapsule] = Field(default_factory=list)
    specials: list[StoreCapsule] = Field(default_factory=list)
    purchase_recommendations: list[StoreCapsule] = Field(default_factory=list)


class ItemsToFeatureResponse(SteamModel):
    """Response of IStoreMarketingService/GetItemsToFeature."""

    response: ItemsToFeature = Field(default_factory=ItemsToFeature)


# -- IStoreQueryService/Query --------------------------------------------------


class StoreQueryResult(SteamModel):
    """Body of IStoreQueryService/Query.

    ``ids`` lists the matches in order; ``store_items`` holds their data when
    a data request was sent.
    """

    metadata: StoreQueryResultMetadata = Field(default_factory=StoreQueryResultMetadata)
    ids: list[StoreItemID] = Field(default_factory=list)
    store_items: list[StoreItem] = Field(default_factory=list)


class StoreQueryResponse(SteamModel):
    """Response of IStoreQueryService/Query."""

    response: StoreQueryResult = Field(default_factory=StoreQueryResult)


# -- IStoreTopSellersService/GetWeeklyTopSellers -------------------------------


class TopSellersRank(SteamModel):
    """An app's place on the weekly top sellers chart."""

    rank: int = 0
    appid: int = 0
    item: StoreItem = Field(
        default_factory=StoreItem, description="Store data, when requested"
    )
    last_week_rank: int = Field(0, description="Rank a week before; 0 when not sent")
    consecutive_weeks: int = Field(0, description="Weeks in a row on the chart")
    first_top100: bool = Field(
        False, description="Unverified: the app's first week in the top 100"
    )


class WeeklyTopSellers(SteamModel):
    """Body of IStoreTopSellersService/GetWeeklyTopSellers: one page of ranks."""

    start_date: int = Field(0, description="Start of the week (Unix time)")
    ranks: list[TopSellersRank] = Field(default_factory=list)
    next_page_start: int = Field(
        0, description="Pass as ``page_start`` for the next page"
    )


class WeeklyTopSellersResponse(SteamModel):
    """Response of IStoreTopSellersService/GetWeeklyTopSellers."""

    response: WeeklyTopSellers = Field(default_factory=WeeklyTopSellers)


# -- ICommunityService/GetApps -------------------------------------------------


class CommunityApp(SteamModel):
    """An app as the Steam Community knows it (``CCDDBAppDetailCommon``)."""

    appid: int = 0
    name: str = ""
    icon: str = Field(
        "",
        description=(
            "Hash of the app's icon; the image is "
            "https://shared.fastly.steamstatic.com/community_assets/images/apps/"
            "<appid>/<icon>.jpg"
        ),
    )
    tool: bool = False
    demo: bool = False
    media: bool = False
    community_visible_stats: bool = Field(
        False, description="Whether the app has stats or achievements to show"
    )
    friendly_name: str = ""
    propagation: str = Field("", description="Steam does not document its values")
    has_adult_content: bool = False
    is_visible_in_steam_china: bool = False
    app_type: int = Field(
        0, description="Kind of app; unverified: presumably an EAppType (1 game)"
    )
    has_adult_content_sex: bool = False
    has_adult_content_violence: bool = False
    content_descriptorids: list[int] = Field(default_factory=list)
    content_descriptorids_including_dlc: list[int] = Field(default_factory=list)


class CommunityApps(SteamModel):
    """Body of ICommunityService/GetApps."""

    apps: list[CommunityApp] = Field(default_factory=list)


class CommunityAppsResponse(SteamModel):
    """Response of ICommunityService/GetApps."""

    response: CommunityApps = Field(default_factory=CommunityApps)


# -- IStoreService/GetGamesFollowed --------------------------------------------


class GamesFollowed(SteamModel):
    """Body of IStoreService/GetGamesFollowed."""

    appids: list[int] = Field(default_factory=list)


class GamesFollowedResponse(SteamModel):
    """Response of IStoreService/GetGamesFollowed."""

    response: GamesFollowed = Field(default_factory=GamesFollowed)


# -- IStoreService/GetTagList --------------------------------------------------


class StoreTag(SteamModel):
    """A store tag and its name in the requested language."""

    tagid: int = 0
    name: str = Field("", description='e.g. "Strategy"')


class TagList(SteamModel):
    """Body of IStoreService/GetTagList."""

    version_hash: str = Field(
        "", description="Pass back as ``have_version_hash`` to skip an unchanged list"
    )
    tags: list[StoreTag] = Field(default_factory=list)


class TagListResponse(SteamModel):
    """Response of IStoreService/GetTagList."""

    response: TagList = Field(default_factory=TagList)


# -- IStoreService/GetUserGameInterestState ------------------------------------


class EStoreDiscoveryQueueType(IntEnum):
    """Kind of discovery queue (``UserGameInterestState.in_queues`` etc.)."""

    NEW = 0
    COMING_SOON = 1
    RECOMMENDED = 2
    EVERY_NEW_RELEASE = 3
    ML_RECOMMENDER = 5
    WISHLIST_ON_SALE = 6
    DLC = 7
    DLC_ON_SALE = 8
    RECOMMENDED_COMING_SOON = 9
    RECOMMENDED_FREE = 10
    RECOMMENDED_ON_SALE = 11
    RECOMMENDED_DEMOS = 12
    DLC_NEW_RELEASES = 13
    DLC_TOP_SELLERS = 14
    DLC_UPCOMING = 15


class EPlaytestStatus(IntEnum):
    """The user's place in an app's playtest (``beta_status``)."""

    NONE = 0
    PENDING = 1
    INVITED = 2
    GRANTED = 3
    EXPIRED = 4


class DiscoveryQueueState(SteamModel):
    """The app in one of the user's discovery queues."""

    # Steam's proto declares k_EStoreDiscoveryQueueTypeNew (0) as the default.
    type: int = Field(0, description="An EStoreDiscoveryQueueType")
    skipped: bool = False
    items_remaining: int = Field(0, description="Items left in the queue")
    next_appid: int = Field(0, description="Next app in the queue")
    experimental_cohort: int = 0


class UserGameInterestState(SteamModel):
    """Body of IStoreService/GetUserGameInterestState: the signed-in user's
    relationship to an app."""

    owned: bool = False
    wishlist: bool = Field(False, description="On the user's wishlist")
    ignored: bool = False
    following: bool = False
    in_queues: list[int] = Field(
        default_factory=list,
        description="EStoreDiscoveryQueueType of each queue the app is in",
    )
    queues_with_skip: list[int] = Field(
        default_factory=list,
        description="EStoreDiscoveryQueueType of each queue where the user skipped it",
    )
    queue_items_remaining: list[int] = Field(
        default_factory=list, description="Items left, in the order of ``in_queues``"
    )
    queue_items_next_appid: list[int] = Field(
        default_factory=list, description="Next app, in the order of ``in_queues``"
    )
    temporarily_owned: bool = Field(
        False, description="Owned for a while only, e.g. a rental or free weekend"
    )
    queues: list[DiscoveryQueueState] = Field(default_factory=list)
    ignored_reason: int = Field(
        0, description="ERecommendationIgnoreReason the user ignored the app for"
    )
    # Steam's proto declares k_ETesterStatusNone (0) as the default.
    beta_status: int = Field(0, description="An EPlaytestStatus")


class UserGameInterestStateResponse(SteamModel):
    """Response of IStoreService/GetUserGameInterestState."""

    response: UserGameInterestState = Field(default_factory=UserGameInterestState)


# -- store.steampowered.com/api/packagedetails ----------------------------------


class PackageApp(SteamModel):
    """An app in a package."""

    id: int = Field(0, description="App id")
    name: str = ""


class PackagePrice(SteamModel):
    """A package's price, in cents of ``currency``."""

    currency: str = Field("", description='e.g. "USD"')
    initial: int = Field(0, description="Price before discount, in cents")
    final: int = Field(0, description="Price after discount, in cents")
    discount_percent: int = 0
    individual: int = Field(
        0,
        description=(
            "Unverified: presumably the apps' total price when bought one by "
            "one, in cents; 0 in some real replies"
        ),
    )


class PackagePlatforms(SteamModel):
    windows: bool = False
    mac: bool = False
    linux: bool = False


class PackageController(SteamModel):
    full_gamepad: bool = Field(False, description="Full controller support")


class PackageReleaseDate(SteamModel):
    coming_soon: bool = False
    date: str = Field("", description='As displayed, e.g. "16 Jul, 2014"; may be ""')


class PackageDetails(SteamModel):
    """A package (sub) from store.steampowered.com/api/packagedetails."""

    name: str = ""
    page_image: str = Field("", description="URL of the package's header image")
    header_image: str = Field(
        "", description="Not in current real replies; kept for older ones"
    )
    small_logo: str = Field("", description="URL of the 231x87 capsule image")
    page_content: str = ""
    apps: list[PackageApp] = Field(default_factory=list)
    price: PackagePrice | None = Field(
        None, description="None when Steam sends no price (unverified: free packages)"
    )
    platforms: PackagePlatforms = Field(default_factory=PackagePlatforms)
    controller: PackageController = Field(default_factory=PackageController)
    release_date: PackageReleaseDate = Field(default_factory=PackageReleaseDate)


# -- store.steampowered.com/appreviews ------------------------------------------


class ReviewAuthor(SteamModel):
    """The author of a review; playtimes are in minutes."""

    steamid: str = Field("", description="SteamID64")
    num_games_owned: int = 0
    num_reviews: int = Field(0, description="Public reviews the author wrote")
    playtime_forever: int = 0
    playtime_last_two_weeks: int = 0
    playtime_at_review: int = 0
    deck_playtime_at_review: int = Field(
        0, description="Steam Deck playtime when the review was written"
    )
    last_played: int = Field(0, description="Unix time")
    personaname: str = ""
    profile_url: str = ""


class AppReview(SteamModel):
    """A user review of an app."""

    recommendationid: str = Field("", description="Review id (64-bit)")
    author: ReviewAuthor = Field(default_factory=ReviewAuthor)
    language: str = Field("", description='Language of the review, e.g. "english"')
    review: str = Field("", description="Text of the review")
    timestamp_created: int = Field(0, description="Unix time")
    timestamp_updated: int = Field(0, description="Unix time")
    voted_up: bool = Field(False, description="True for a positive review")
    votes_up: int = Field(0, description="Users who found it helpful")
    votes_funny: int = Field(0, description="Users who found it funny")
    # Steam sends it as a string ("0.57925105094909668") or as a number (0.5).
    weighted_vote_score: float = Field(0.0, description="Helpfulness score")
    comment_count: int = 0
    steam_purchase: bool = Field(False, description="Bought on Steam")
    received_for_free: bool = Field(
        False, description="The author ticked that they got it for free"
    )
    refunded: bool = False
    written_during_early_access: bool = False
    primarily_steam_deck: bool = Field(
        False, description="Played mostly on Steam Deck when written"
    )
    developer_response: str = ""
    timestamp_dev_responded: int = Field(0, description="Unix time")
    app_release_date: int = Field(0, description="Unix time")
    reactions: list[Any] = Field(
        default_factory=list, description="Award reactions, raw JSON"
    )


class ReviewQuerySummary(SteamModel):
    """Totals of a review query.

    ``num_reviews`` counts the reviews on this page. Steam documents that
    the score and totals come only with the first page (cursor "*"), and
    only when ``review_type`` is "all"; otherwise they keep their defaults.
    """

    num_reviews: int = 0
    review_score: int = Field(0, description="An EUserReviewScore")
    review_score_desc: str = Field("", description='e.g. "Very Positive"')
    total_positive: int = 0
    total_negative: int = 0
    total_reviews: int = 0


class AppReviews(SteamModel):
    """One page of store.steampowered.com/appreviews/<appid>?json=1."""

    success: int = Field(0, description="1 when Steam answered the query")
    query_summary: ReviewQuerySummary = Field(default_factory=ReviewQuerySummary)
    reviews: list[AppReview] = Field(default_factory=list)
    cursor: str = Field("", description="Pass as ``cursor`` for the next page")
