"""Models for Steam Workshop responses: IPublishedFileService and
ISteamRemoteStorage.

IPublishedFileService methods serialize protobuf messages to JSON and leave
out every field at its default value, so every field here has a default.
64-bit ids (published file ids, Steam IDs, content handles) arrive as strings
and are kept as strings; 64-bit counts and sizes arrive as strings too and are
read as ``int``. Proto enums are kept as ``int`` so unknown values still parse.

ISteamRemoteStorage/GetPublishedFileDetails is an older endpoint with its own
field names; an item Steam cannot find comes back with only its id and a
``result`` other than 1.
"""

from enum import IntEnum
from typing import Any

from pydantic import Field

from .base import SteamModel


class EPublishedFileQueryType(IntEnum):
    """Order (and filter) of a Workshop query (``query_type`` of QueryFiles)."""

    RANKED_BY_VOTE = 0
    RANKED_BY_PUBLICATION_DATE = 1
    ACCEPTED_FOR_GAME_RANKED_BY_ACCEPTANCE_DATE = 2
    RANKED_BY_TREND = 3
    FAVORITED_BY_FRIENDS_RANKED_BY_PUBLICATION_DATE = 4
    CREATED_BY_FRIENDS_RANKED_BY_PUBLICATION_DATE = 5
    RANKED_BY_NUM_TIMES_REPORTED = 6
    CREATED_BY_FOLLOWED_USERS_RANKED_BY_PUBLICATION_DATE = 7
    NOT_YET_RATED = 8
    RANKED_BY_TOTAL_UNIQUE_SUBSCRIPTIONS = 9
    RANKED_BY_TOTAL_VOTES_ASC = 10
    RANKED_BY_VOTES_UP = 11
    RANKED_BY_TEXT_SEARCH = 12
    RANKED_BY_PLAYTIME_TREND = 13
    RANKED_BY_TOTAL_PLAYTIME = 14
    RANKED_BY_AVERAGE_PLAYTIME_TREND = 15
    RANKED_BY_LIFETIME_AVERAGE_PLAYTIME = 16
    RANKED_BY_PLAYTIME_SESSIONS_TREND = 17
    RANKED_BY_LIFETIME_PLAYTIME_SESSIONS = 18
    RANKED_BY_INAPPROPRIATE_CONTENT_RATING = 19
    RANKED_BY_BAN_CONTENT_CHECK = 20
    RANKED_BY_LAST_UPDATED_DATE = 21
    RANKED_BY_NUM_PARENT_ITEMS = 22
    RANKED_BY_NUM_PARENT_COLLECTIONS = 23


class PublishedFileTag(SteamModel):
    tag: str = ""
    adminonly: bool = False
    display_name: str = Field("", description="Localized tag name")


class PublishedFileVoteData(SteamModel):
    score: float = Field(0.0, description="Rating between 0 and 1")
    votes_up: int = 0
    votes_down: int = 0
    trusted_score: float = 0.0
    trusted_votes_up: int = 0
    trusted_votes_down: int = 0


class PublishedFilePreview(SteamModel):
    """An additional preview image or video of an item."""

    previewid: str = Field("", description="Preview id (64-bit)")
    sortorder: int = 0
    url: str = Field("", description="Image URL")
    size: int = Field(0, description="Image size in bytes")
    filename: str = ""
    youtubevideoid: str = Field("", description="YouTube video id of a video")
    preview_type: int = Field(0, description="Kind of preview (EItemPreviewType)")
    external_reference: str = ""


class PublishedFileChild(SteamModel):
    """An item in a collection, or an item another item depends on."""

    publishedfileid: str = ""
    sortorder: int = 0
    file_type: int = Field(0, description="EWorkshopFileType of the child")


class PublishedFileKVTag(SteamModel):
    key: str = ""
    value: str = ""


class PublishedFileForSaleData(SteamModel):
    is_for_sale: bool = False
    price_category: int = 0
    estatus: int = Field(0, description="Sale status (EPublishedFileForSaleStatus)")
    price_category_floor: int = 0
    price_is_pay_what_you_want: bool = False
    discount_percentage: int = 0


class PublishedFilePlaytimeStats(SteamModel):
    playtime_seconds: int = 0
    num_sessions: int = 0


class PublishedFileReaction(SteamModel):
    reactionid: int = 0
    count: int = 0


class PublishedFileDetails(SteamModel):
    """A Workshop item (or collection, guide, artwork...) from
    IPublishedFileService.

    Which optional parts are filled depends on what the request asked for
    (tags, previews, children, key-value tags, votes, ...).
    """

    result: int = Field(0, description="EResult: 1 if the item was found")
    publishedfileid: str = Field("", description="Published file id (64-bit)")
    creator: str = Field("", description="Steam ID of the author")
    creator_appid: int = Field(0, description="App the item was created with")
    consumer_appid: int = Field(0, description="App the item is for")
    consumer_shortcutid: int = 0
    filename: str = ""
    file_size: int = Field(0, description="Size of the content in bytes")
    preview_file_size: int = Field(0, description="Size of the preview in bytes")
    file_url: str = ""
    preview_url: str = Field("", description="URL of the main preview image")
    youtubevideoid: str = ""
    url: str = ""
    hcontent_file: str = Field("", description="Content handle (64-bit)")
    hcontent_preview: str = Field("", description="Preview handle (64-bit)")
    title: str = ""
    file_description: str = ""
    short_description: str = Field(
        "", description="Set instead of file_description when requested"
    )
    time_created: int = Field(0, description="Unix timestamp of publication")
    time_updated: int = Field(0, description="Unix timestamp of the last update")
    visibility: int = Field(
        0, description="Visibility (ERemoteStoragePublishedFileVisibility)"
    )
    flags: int = 0
    workshop_file: bool = False
    workshop_accepted: bool = Field(
        False, description="Whether the developer accepted the item into the game"
    )
    show_subscribe_all: bool = False
    num_comments_developer: int = 0
    num_comments_public: int = 0
    banned: bool = False
    ban_reason: str = ""
    banner: str = Field("", description="Steam ID of who banned the item")
    can_be_deleted: bool = False
    incompatible: bool = False
    app_name: str = ""
    file_type: int = Field(0, description="Kind of item (EWorkshopFileType)")
    can_subscribe: bool = False
    subscriptions: int = Field(0, description="Current subscribers")
    favorited: int = Field(0, description="Users who currently favorite the item")
    followers: int = 0
    lifetime_subscriptions: int = 0
    lifetime_favorited: int = 0
    lifetime_followers: int = 0
    lifetime_playtime: int = Field(0, description="Total playtime in seconds")
    lifetime_playtime_sessions: int = 0
    views: int = 0
    image_width: int = 0
    image_height: int = 0
    image_url: str = ""
    spoiler_tag: bool = False
    shortcutid: int = 0
    shortcutname: str = ""
    num_children: int = 0
    num_reports: int = 0
    previews: list[PublishedFilePreview] = Field(default_factory=list)
    tags: list[PublishedFileTag] = Field(default_factory=list)
    children: list[PublishedFileChild] = Field(default_factory=list)
    kvtags: list[PublishedFileKVTag] = Field(default_factory=list)
    vote_data: PublishedFileVoteData = Field(default_factory=PublishedFileVoteData)
    time_subscribed: int = 0
    for_sale_data: PublishedFileForSaleData = Field(
        default_factory=PublishedFileForSaleData
    )
    metadata: str = Field("", description="Developer metadata, when requested")
    language: int = Field(0, description="Language of the text (ELanguage)")
    playtime_stats: PublishedFilePlaytimeStats = Field(
        default_factory=PublishedFilePlaytimeStats,
        description="Playtime over the requested number of days",
    )
    maybe_inappropriate_sex: bool = False
    maybe_inappropriate_violence: bool = False
    revision_change_number: int = 0
    revision: int = Field(0, description="Revision returned (EPublishedFileRevision)")
    available_revisions: list[int] = Field(default_factory=list)
    reactions: list[PublishedFileReaction] = Field(default_factory=list)
    ban_text_check_result: int = 0
    content_descriptorids: list[int] = Field(
        default_factory=list, description="Content descriptors (EContentDescriptorID)"
    )
    search_score: float = 0.0
    external_asset_id: str = ""
    author_snapshots: list[dict[str, Any]] = Field(default_factory=list)


class PublishedFileDetailsList(SteamModel):
    publishedfiledetails: list[PublishedFileDetails] = Field(default_factory=list)


class PublishedFileDetailsResponse(SteamModel):
    """IPublishedFileService/GetDetails: one entry per requested id, in order."""

    response: PublishedFileDetailsList = Field(default_factory=PublishedFileDetailsList)


class QueryFilesResult(SteamModel):
    total: int = Field(0, description="Number of items matching the query")
    publishedfiledetails: list[PublishedFileDetails] = Field(default_factory=list)
    next_cursor: str = Field(
        "", description="Cursor of the next page, when a cursor was sent"
    )


class QueryFilesResponse(SteamModel):
    """IPublishedFileService/QueryFiles: one page of matching items."""

    response: QueryFilesResult = Field(default_factory=QueryFilesResult)


class RemoteStorageTag(SteamModel):
    tag: str = ""


class RemoteStorageFileDetails(SteamModel):
    """A Workshop item from ISteamRemoteStorage/GetPublishedFileDetails."""

    publishedfileid: str = Field("", description="Published file id (64-bit)")
    result: int = Field(0, description="EResult: 1 if the item was found")
    creator: str = Field("", description="Steam ID of the author")
    creator_app_id: int = Field(0, description="App the item was created with")
    consumer_app_id: int = Field(0, description="App the item is for")
    filename: str = ""
    file_size: int = Field(0, description="Size of the content in bytes")
    file_url: str = ""
    hcontent_file: str = Field("", description="Content handle (64-bit)")
    preview_url: str = ""
    hcontent_preview: str = Field("", description="Preview handle (64-bit)")
    title: str = ""
    description: str = ""
    time_created: int = Field(0, description="Unix timestamp of publication")
    time_updated: int = Field(0, description="Unix timestamp of the last update")
    visibility: int = Field(
        0, description="Visibility (ERemoteStoragePublishedFileVisibility)"
    )
    banned: bool = False
    ban_reason: str = ""
    subscriptions: int = 0
    favorited: int = 0
    lifetime_subscriptions: int = 0
    lifetime_favorited: int = 0
    views: int = 0
    tags: list[RemoteStorageTag] = Field(default_factory=list)


class RemoteStorageFileDetailsList(SteamModel):
    result: int = Field(0, description="EResult of the whole request")
    resultcount: int = 0
    publishedfiledetails: list[RemoteStorageFileDetails] = Field(default_factory=list)


class RemoteStorageFileDetailsResponse(SteamModel):
    """ISteamRemoteStorage/GetPublishedFileDetails: one entry per id, in order."""

    response: RemoteStorageFileDetailsList = Field(
        default_factory=RemoteStorageFileDetailsList
    )


class EUCMListType(IntEnum):
    """A user's Workshop list (``list_type`` of Subscribe and Unsubscribe).

    Values from the Steam client's ``EUCMListType`` as published by
    OpenSteamworks and opensteamworks' enums.steamd.
    """

    SUBSCRIBED = 1
    FAVORITES = 2
    PLAYED = 3
    COMPLETED = 4
    SHORTCUT_FAVORITES = 5
    FOLLOWED = 6


# -- IPublishedFileService/GetUserFiles -------------------------------------------


class UserFilesApp(SteamModel):
    """An app the returned items belong to
    (``CPublishedFile_GetUserFiles_Response_App``)."""

    appid: int = 0
    name: str = ""
    shortcutid: int = 0
    private: bool = False


class UserFilesResult(SteamModel):
    """``CPublishedFile_GetUserFiles_Response``: one page of a user's items."""

    total: int = Field(0, description="Number of items matching the request")
    startindex: int = Field(
        0, description="Position of the page's first item, counted from 1"
    )
    publishedfiledetails: list[PublishedFileDetails] = Field(default_factory=list)
    apps: list[UserFilesApp] = Field(
        default_factory=list, description="Filled when return_apps is set"
    )


class UserFilesResponse(SteamModel):
    """IPublishedFileService/GetUserFiles: one page of a user's items."""

    response: UserFilesResult = Field(default_factory=UserFilesResult)


# -- IPublishedFileService/Subscribe and Unsubscribe ------------------------------


class EmptyServiceResult(SteamModel):
    """An empty response message (``CPublishedFile_Subscribe_Response``,
    ``CPublishedFile_Unsubscribe_Response``)."""


class EmptyServiceResponse(SteamModel):
    """Response of a service method whose response message has no fields."""

    response: EmptyServiceResult = Field(default_factory=EmptyServiceResult)


# -- ISteamRemoteStorage/GetCollectionDetails -------------------------------------


class CollectionChild(SteamModel):
    """An item in a collection."""

    publishedfileid: str = Field("", description="Published file id (64-bit)")
    sortorder: int = Field(0, description="Position in the collection")
    filetype: int = Field(0, description="Kind of item (EWorkshopFileType)")


class CollectionDetails(SteamModel):
    """A collection from ISteamRemoteStorage/GetCollectionDetails.

    A collection Steam cannot find comes back with only its id and a
    ``result`` other than 1.
    """

    publishedfileid: str = Field("", description="Published file id (64-bit)")
    result: int = Field(0, description="EResult: 1 if the collection was found")
    children: list[CollectionChild] = Field(default_factory=list)


class CollectionDetailsList(SteamModel):
    result: int = Field(0, description="EResult of the whole request")
    resultcount: int = 0
    collectiondetails: list[CollectionDetails] = Field(default_factory=list)


class CollectionDetailsResponse(SteamModel):
    """ISteamRemoteStorage/GetCollectionDetails: the requested collections."""

    response: CollectionDetailsList = Field(default_factory=CollectionDetailsList)
