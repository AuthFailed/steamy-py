"""Workshop endpoints (steam.workshop)."""

import re
from collections.abc import AsyncIterator, Iterable
from typing import Any

from ..exceptions import SteamAPIError
from ..models.workshop import (
    CollectionDetailsList,
    CollectionDetailsResponse,
    EmptyServiceResponse,
    EPublishedFileQueryType,
    EUCMListType,
    PublishedFileDetails,
    PublishedFileDetailsList,
    PublishedFileDetailsResponse,
    QueryFilesResponse,
    QueryFilesResult,
    RemoteStorageFileDetailsList,
    RemoteStorageFileDetailsResponse,
    UserFilesResponse,
    UserFilesResult,
)
from ..steamid import SteamIDLike, validate_app_id, validate_steam_id
from .base import BaseAPI

_SERVICE = "IPublishedFileService"

# Published file ids are 64-bit; pass them as int or as the string Steam
# returns.
PublishedFileID = int | str

_UINT64_MAX = 2**64 - 1
_DIGITS_RE = re.compile(r"[0-9]{1,20}", re.ASCII)


def _publishedfileid(value: object) -> str:
    """Check one published file id (a positive 64-bit int, or its decimal
    string; not a ``bool``) and return it as a decimal string."""
    number = value
    if isinstance(value, str) and _DIGITS_RE.fullmatch(value):
        number = int(value)
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not 0 < number <= _UINT64_MAX
    ):
        raise ValueError(f"Invalid published file id: {value!r}")
    return str(int(number))


def _publishedfileids(
    values: PublishedFileID | Iterable[PublishedFileID],
) -> list[str]:
    """Check one published file id or several; a str counts as one id, and
    byte buffers are rejected rather than read as a sequence of ints."""
    if isinstance(values, int | str | bytes | bytearray | memoryview) or not (
        isinstance(values, Iterable)
    ):
        ids = [_publishedfileid(values)]
    else:
        ids = [_publishedfileid(value) for value in values]
    if not ids:
        raise ValueError("At least one published file id must be provided")
    return ids


def _app_id(value: int | None) -> int | None:
    """Validate an optional App ID input."""
    return None if value is None else validate_app_id(value)


def _tags(value: str | Iterable[str] | None) -> list[str] | None:
    """One tag or several; a str counts as one tag. Byte buffers are rejected
    rather than read as a sequence of ints."""
    if value is None:
        return None
    if isinstance(value, bytes | bytearray | memoryview):
        raise TypeError(f"Tags must be str, not {type(value).__name__}")
    return [value] if isinstance(value, str) else list(value)


class WorkshopAPI(BaseAPI):
    """Steam Workshop items (IPublishedFileService, ISteamRemoteStorage)."""

    async def get_details(
        self,
        publishedfileids: PublishedFileID | Iterable[PublishedFileID],
        *,
        includetags: bool = False,
        includeadditionalpreviews: bool = False,
        includechildren: bool = False,
        includekvtags: bool = False,
        includevotes: bool = False,
        short_description: bool = False,
        includeforsaledata: bool = False,
        includemetadata: bool = False,
        language: int = 0,
        return_playtime_stats: int | None = None,
        appid: int | None = None,
        strip_description_bbcode: bool = False,
        includereactions: bool = False,
    ) -> PublishedFileDetailsList:
        """Get Workshop items by id (IPublishedFileService/GetDetails).

        Sends the API key if the client has one, else the access token.
        Each requested id gets an entry, in order; check its ``result``
        (1 if the item was found).

        Args:
            publishedfileids: One published file id or several
            includetags: Return tags (``tags``)
            includeadditionalpreviews: Return the extra preview images and
                videos (``previews``)
            includechildren: Return the items of a collection, or the items
                an item requires (``children``)
            includekvtags: Return key-value tags (``kvtags``)
            includevotes: Return vote counts and score (``vote_data``)
            short_description: Fill ``short_description`` instead of
                ``file_description``
            includeforsaledata: Return pricing data (``for_sale_data``)
            includemetadata: Return developer metadata (``metadata``)
            language: Language of titles and descriptions, as an ELanguage
                number; 0 (the default) is English
            return_playtime_stats: Return playtime over this many days
                before today (``playtime_stats``)
            appid: App the items belong to
            strip_description_bbcode: Remove BBCode from descriptions
            includereactions: Return award reactions (``reactions``)

        Returns:
            The items, in ``publishedfiledetails``

        Raises:
            ValueError: If no id is given or an id is not a valid published
                file id
            InvalidAppIDError: If ``appid`` is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        inputs = {
            "publishedfileids": _publishedfileids(publishedfileids),
            "includetags": includetags,
            "includeadditionalpreviews": includeadditionalpreviews,
            "includechildren": includechildren,
            "includekvtags": includekvtags,
            "includevotes": includevotes,
            "short_description": short_description,
            "includeforsaledata": includeforsaledata,
            "includemetadata": includemetadata,
            "language": language,
            "return_playtime_stats": return_playtime_stats,
            "appid": _app_id(appid),
            "strip_description_bbcode": strip_description_bbcode,
            "includereactions": includereactions,
        }
        result = await self._call_service(
            _SERVICE,
            "GetDetails",
            "get workshop item details",
            inputs,
            model=PublishedFileDetailsResponse,
            auth_type="any",
        )
        return result.response

    async def query_files(
        self,
        query_type: int = EPublishedFileQueryType.RANKED_BY_VOTE,
        *,
        appid: int | None = None,
        creator_appid: int | None = None,
        page: int | None = None,
        cursor: str | None = None,
        numperpage: int | None = None,
        requiredtags: str | Iterable[str] | None = None,
        excludedtags: str | Iterable[str] | None = None,
        match_all_tags: bool | None = None,
        search_text: str | None = None,
        filetype: int | None = None,
        child_publishedfileid: PublishedFileID | None = None,
        days: int | None = None,
        include_recent_votes_only: bool | None = None,
        cache_max_age_seconds: int | None = None,
        language: int = 0,
        totalonly: bool | None = None,
        ids_only: bool | None = None,
        return_details: bool = True,
        return_vote_data: bool = False,
        return_tags: bool = False,
        return_kv_tags: bool = False,
        return_previews: bool = False,
        return_children: bool = False,
        return_short_description: bool = False,
        return_for_sale_data: bool = False,
        return_metadata: bool = False,
        return_playtime_stats: int | None = None,
        return_reactions: bool = False,
        strip_description_bbcode: bool = False,
    ) -> QueryFilesResult:
        """Search the Workshop (IPublishedFileService/QueryFiles).

        Sends the API key if the client has one, else the access token.
        Pages with a cursor unless ``page`` is given: pass the response's
        ``next_cursor`` back as ``cursor`` for the next page, or use
        ``iter_query_files``.

        Args:
            query_type: Order of the results (``EPublishedFileQueryType``)
            appid: App the items are for
            creator_appid: App the items were created with
            page: Page number, for page-number paging
            cursor: A previous page's ``next_cursor``; the first page's
                cursor, "*", is sent when neither ``cursor`` nor ``page`` is
                given. Steam ignores ``page`` when a cursor is sent.
            numperpage: Items per page; Steam's default is 1
            requiredtags: Only items with these tags (one tag or several)
            excludedtags: Only items without these tags
            match_all_tags: True (Steam's default): items need every
                required tag; False: at least one of them
            search_text: Text to find in titles and descriptions
            filetype: Kind of items (EPublishedFileInfoMatchingFileType)
            child_publishedfileid: Only items that reference this item
            days: For ``RANKED_BY_TREND``, the number of days of votes to
                rank by (1 to 7)
            include_recent_votes_only: For ``RANKED_BY_TREND``, only items
                with votes within ``days``
            cache_max_age_seconds: Accept results cached up to this long
            language: Language to search in and return text in, as an
                ELanguage number; 0 (the default) is English
            totalonly: Return only ``total``
            ids_only: Return only the ids of the items
            return_details: Return the standard set of item details;
                otherwise Steam returns little more than vote data unless
                another ``return_*`` flag is set
            return_vote_data: Return vote counts and score (``vote_data``)
            return_tags: Return tags (``tags``)
            return_kv_tags: Return key-value tags (``kvtags``)
            return_previews: Return the extra preview images and videos
                (``previews``)
            return_children: Return child item ids (``children``)
            return_short_description: Fill ``short_description`` instead of
                ``file_description``
            return_for_sale_data: Return pricing data (``for_sale_data``)
            return_metadata: Return developer metadata (``metadata``)
            return_playtime_stats: Return playtime over this many days
                before today (``playtime_stats``)
            return_reactions: Return award reactions (``reactions``)
            strip_description_bbcode: Remove BBCode from descriptions

        Returns:
            One page: ``total``, ``publishedfiledetails`` and ``next_cursor``

        Raises:
            ValueError: If ``child_publishedfileid`` is invalid
            InvalidAppIDError: If ``appid`` or ``creator_appid`` is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        if cursor is None and page is None:
            cursor = "*"
        if child_publishedfileid is not None:
            child_publishedfileid = _publishedfileid(child_publishedfileid)
        inputs = {
            "query_type": query_type,
            "page": page,
            "cursor": cursor,
            "numperpage": numperpage,
            "creator_appid": _app_id(creator_appid),
            "appid": _app_id(appid),
            "requiredtags": _tags(requiredtags),
            "excludedtags": _tags(excludedtags),
            "match_all_tags": match_all_tags,
            "search_text": search_text,
            "filetype": filetype,
            "child_publishedfileid": child_publishedfileid,
            "days": days,
            "include_recent_votes_only": include_recent_votes_only,
            "cache_max_age_seconds": cache_max_age_seconds,
            "language": language,
            "totalonly": totalonly,
            "ids_only": ids_only,
            "return_details": return_details,
            "return_vote_data": return_vote_data,
            "return_tags": return_tags,
            "return_kv_tags": return_kv_tags,
            "return_previews": return_previews,
            "return_children": return_children,
            "return_short_description": return_short_description,
            "return_for_sale_data": return_for_sale_data,
            "return_metadata": return_metadata,
            "return_playtime_stats": return_playtime_stats,
            "return_reactions": return_reactions,
            "strip_description_bbcode": strip_description_bbcode,
        }
        result = await self._call_service(
            _SERVICE,
            "QueryFiles",
            "query workshop files",
            inputs,
            model=QueryFilesResponse,
            auth_type="any",
        )
        return result.response

    async def iter_query_files(
        self,
        query_type: int = EPublishedFileQueryType.RANKED_BY_VOTE,
        *,
        numperpage: int = 100,
        **filters: Any,
    ) -> AsyncIterator[PublishedFileDetails]:
        """Iterate over every item a Workshop query matches.

        Follows ``next_cursor`` one page request at a time, and stops when a
        page is empty, has no ``next_cursor``, or returns the cursor it was
        sent.

        Args:
            query_type: Order of the results (``EPublishedFileQueryType``)
            numperpage: Page size
            **filters: Other arguments of ``query_files``, except ``page``
                and ``cursor``

        Yields:
            The matching items, in query order

        Raises:
            TypeError: If ``page`` or ``cursor`` is given
            ValueError: If ``child_publishedfileid`` is invalid
            InvalidAppIDError: If ``appid`` or ``creator_appid`` is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If a response has an unexpected shape
            SteamAPIError: On API errors
        """
        if "page" in filters or "cursor" in filters:
            raise TypeError("iter_query_files pages by itself; omit page and cursor")
        cursor = "*"
        while True:
            result = await self.query_files(
                query_type, cursor=cursor, numperpage=numperpage, **filters
            )
            items = result.publishedfiledetails
            for item in items:
                yield item
            next_cursor = result.next_cursor
            if not items or not next_cursor or next_cursor == cursor:
                return
            cursor = next_cursor

    async def get_published_file_details(
        self, publishedfileids: PublishedFileID | Iterable[PublishedFileID]
    ) -> RemoteStorageFileDetailsList:
        """Get Workshop items by id (ISteamRemoteStorage/GetPublishedFileDetails).

        Needs no credential and sends none. Each requested id gets an entry,
        in order; check its ``result`` (1 if the item was found). For more
        detail (votes, previews, children) use ``get_details``.

        Args:
            publishedfileids: One published file id or several

        Returns:
            The items, in ``publishedfiledetails``

        Raises:
            ValueError: If no id is given or an id is not a valid published
                file id
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        ids = _publishedfileids(publishedfileids)
        result = await self._call_service(
            "ISteamRemoteStorage",
            "GetPublishedFileDetails",
            "get published file details",
            {"itemcount": len(ids), "publishedfileids": ids},
            model=RemoteStorageFileDetailsResponse,
            http_method="POST",
            auth_type="none",
        )
        return result.response

    async def get_user_files(
        self,
        steamid: SteamIDLike,
        *,
        appid: int | None = None,
        page: int | None = None,
        numperpage: int | None = None,
        type: str | None = None,
        sortmethod: str | None = None,
        privacy: int | None = None,
        requiredtags: str | Iterable[str] | None = None,
        excludedtags: str | Iterable[str] | None = None,
        filetype: int | None = None,
        creator_appid: int | None = None,
        match_cloud_filename: str | None = None,
        cache_max_age_seconds: int | None = None,
        language: int = 0,
        totalonly: bool | None = None,
        ids_only: bool | None = None,
        return_vote_data: bool = True,
        return_tags: bool = False,
        return_kv_tags: bool = True,
        return_previews: bool = False,
        return_children: bool = False,
        return_short_description: bool = True,
        return_for_sale_data: bool = False,
        return_metadata: bool = False,
        return_playtime_stats: int | None = None,
        return_reactions: bool = False,
        return_apps: bool = False,
        strip_description_bbcode: bool | None = None,
    ) -> UserFilesResult:
        """Get one page of a user's Workshop items.

        Calls IPublishedFileService/GetUserFiles with the API key if the
        client has one, else the access token.
        Pages by page number; ``iter_user_files`` walks every page. The
        ``return_*`` defaults are the defaults of Steam's proto, which
        differ from ``query_files``: vote data, key-value tags and short
        descriptions are on.

        Args:
            steamid: Steam ID of the user (int, str or SteamID)
            appid: App the items were published to
            page: Page number, from 1 (Steam's default)
            numperpage: Items per page; Steam's default is 1
            type: Which of the user's lists: Steam's default is "myfiles"
                (the items the user published); other clients use
                "mysubscriptions" and "myfavorites"
            sortmethod: Order, as Steam's sort method name; Steam's default
                is "lastupdated"
            privacy: Visibility filter, passed as is (Steam does not
                document its values)
            requiredtags: Only items with these tags (one tag or several)
            excludedtags: Only items without these tags
            filetype: Kind of items (EPublishedFileInfoMatchingFileType)
            creator_appid: Only items created with this app
            match_cloud_filename: Only items with this cloud file name
            cache_max_age_seconds: Accept results cached up to this long
            language: Language of titles and descriptions, as an ELanguage
                number; 0 (the default) is English
            totalonly: Return only ``total``
            ids_only: Return only the ids of the items
            return_vote_data: Return vote counts and score (``vote_data``)
            return_tags: Return tags (``tags``)
            return_kv_tags: Return key-value tags (``kvtags``)
            return_previews: Return the extra preview images and videos
                (``previews``)
            return_children: Return child item ids (``children``)
            return_short_description: Fill ``short_description`` instead of
                ``file_description``
            return_for_sale_data: Return pricing data (``for_sale_data``)
            return_metadata: Return developer metadata (``metadata``)
            return_playtime_stats: Return playtime over this many days
                before today (``playtime_stats``)
            return_reactions: Return award reactions (``reactions``)
            return_apps: Return the apps the items belong to (``apps``)
            strip_description_bbcode: Remove BBCode from descriptions

        Returns:
            One page: ``total``, ``startindex`` (the position of the page's
            first item, from 1), ``publishedfiledetails`` and ``apps``

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            InvalidAppIDError: If ``appid`` or ``creator_appid`` is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        inputs = {
            "steamid": validate_steam_id(steamid),
            "appid": _app_id(appid),
            "page": page,
            "numperpage": numperpage,
            "type": type,
            "sortmethod": sortmethod,
            "privacy": privacy,
            "requiredtags": _tags(requiredtags),
            "excludedtags": _tags(excludedtags),
            "filetype": filetype,
            "creator_appid": _app_id(creator_appid),
            "match_cloud_filename": match_cloud_filename,
            "cache_max_age_seconds": cache_max_age_seconds,
            "language": language,
            "totalonly": totalonly,
            "ids_only": ids_only,
            "return_vote_data": return_vote_data,
            "return_tags": return_tags,
            "return_kv_tags": return_kv_tags,
            "return_previews": return_previews,
            "return_children": return_children,
            "return_short_description": return_short_description,
            "return_for_sale_data": return_for_sale_data,
            "return_metadata": return_metadata,
            "return_playtime_stats": return_playtime_stats,
            "return_reactions": return_reactions,
            "return_apps": return_apps,
            "strip_description_bbcode": strip_description_bbcode,
        }
        result = await self._call_service(
            _SERVICE,
            "GetUserFiles",
            "get user workshop files",
            inputs,
            model=UserFilesResponse,
            auth_type="any",
        )
        return result.response

    async def iter_user_files(
        self, steamid: SteamIDLike, *, numperpage: int = 50, **filters: Any
    ) -> AsyncIterator[PublishedFileDetails]:
        """Iterate over all of a user's Workshop items, page by page.

        Requests pages 1, 2, ... one at a time and stops at an empty page or
        once ``total`` items have come back. Each page's ``startindex`` is
        checked, so a page size Steam does not honour raises instead of
        skipping items.

        Args:
            steamid: Steam ID of the user (int, str or SteamID)
            numperpage: Page size
            **filters: Other arguments of ``get_user_files``, except ``page``

        Yields:
            The user's items, in Steam's order

        Raises:
            TypeError: If ``page`` is given
            InvalidSteamIDError: If the Steam ID is invalid
            InvalidAppIDError: If ``appid`` or ``creator_appid`` is invalid
            AuthenticationError: If the client has neither an API key nor an
                access token
            ResponseParsingError: If a response has an unexpected shape
            SteamAPIError: On API errors, or if a page does not start where
                the previous one ended
        """
        if "page" in filters:
            raise TypeError("iter_user_files pages by itself; omit page")
        page = 1
        seen = 0
        while True:
            result = await self.get_user_files(
                steamid, page=page, numperpage=numperpage, **filters
            )
            items = result.publishedfiledetails
            if items and result.startindex and result.startindex != seen + 1:
                raise SteamAPIError(
                    f"Steam returned page {page} from item {result.startindex}, "
                    f"expected item {seen + 1}; is numperpage={numperpage} "
                    "too large?"
                )
            for item in items:
                yield item
            seen += len(items)
            if not items or seen >= result.total:
                return
            page += 1

    async def subscribe(
        self,
        publishedfileid: PublishedFileID,
        *,
        list_type: int = EUCMListType.SUBSCRIBED,
        appid: int | None = None,
        notify_client: bool = False,
        include_dependencies: bool = False,
    ) -> None:
        """Adds a Workshop item to one of the signed-in user's lists.

        By default this subscribes the user to the item. Calls
        IPublishedFileService/Subscribe (POST) with the access token, which
        identifies the user; the inputs go in the form body. Steam answers
        with an empty response; a refusal comes as a failing ``x-eresult``.

        Args:
            publishedfileid: The item (int, or the decimal string Steam
                returns)
            list_type: Which list (``EUCMListType``); ``SUBSCRIBED`` (1), the
                value other clients send, by default
            appid: App the item belongs to; left out when None, as other
                clients do (unverified whether Steam checks it)
            notify_client: Tell the user's running Steam client about the
                change (unverified: so that it downloads the item)
            include_dependencies: Also subscribe to the items this item
                requires (unverified)

        Raises:
            ValueError: If ``publishedfileid`` is not a valid published file
                id
            InvalidAppIDError: If ``appid`` is invalid
            AuthenticationError: If the client has no access token, or Steam
                rejects it
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On other API errors, e.g. a failing ``x-eresult``
        """
        await self._call_service(
            _SERVICE,
            "Subscribe",
            "subscribe to workshop item",
            {
                "publishedfileid": _publishedfileid(publishedfileid),
                "list_type": list_type,
                "appid": _app_id(appid),
                "notify_client": notify_client,
                "include_dependencies": include_dependencies,
            },
            model=EmptyServiceResponse,
            http_method="POST",
            auth_type="access_token",
        )

    async def unsubscribe(
        self,
        publishedfileid: PublishedFileID,
        *,
        list_type: int = EUCMListType.SUBSCRIBED,
        appid: int | None = None,
        notify_client: bool = False,
    ) -> None:
        """Removes a Workshop item from one of the signed-in user's lists.

        By default this unsubscribes the user from the item. Calls
        IPublishedFileService/Unsubscribe (POST) with the access token,
        which identifies the user; the inputs go in the form body. Steam
        answers with an empty response; a refusal comes as a failing
        ``x-eresult``.

        Args:
            publishedfileid: The item (int, or the decimal string Steam
                returns)
            list_type: Which list (``EUCMListType``); ``SUBSCRIBED`` (1) by
                default
            appid: App the item belongs to; left out when None (unverified
                whether Steam checks it)
            notify_client: Tell the user's running Steam client about the
                change (unverified: so that it removes the item)

        Raises:
            ValueError: If ``publishedfileid`` is not a valid published file
                id
            InvalidAppIDError: If ``appid`` is invalid
            AuthenticationError: If the client has no access token, or Steam
                rejects it
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On other API errors, e.g. a failing ``x-eresult``
        """
        await self._call_service(
            _SERVICE,
            "Unsubscribe",
            "unsubscribe from workshop item",
            {
                "publishedfileid": _publishedfileid(publishedfileid),
                "list_type": list_type,
                "appid": _app_id(appid),
                "notify_client": notify_client,
            },
            model=EmptyServiceResponse,
            http_method="POST",
            auth_type="access_token",
        )

    async def get_collection_details(
        self, collection_ids: PublishedFileID | Iterable[PublishedFileID]
    ) -> CollectionDetailsList:
        """Get the items in Workshop collections.

        Calls ISteamRemoteStorage/GetCollectionDetails, which needs no
        credential, and sends none; the ids go in a POST form body.
        Check each collection's ``result`` (1 if it was found). Children
        are listed by id only; look them up with ``get_details``.

        Args:
            collection_ids: One collection's published file id or several

        Returns:
            The collections, in ``collectiondetails``

        Raises:
            ValueError: If no id is given or an id is not a valid published
                file id
            ResponseParsingError: If the response has an unexpected shape
            SteamAPIError: On API errors
        """
        ids = _publishedfileids(collection_ids)
        result = await self._call_service(
            "ISteamRemoteStorage",
            "GetCollectionDetails",
            "get collection details",
            {"collectioncount": len(ids), "publishedfileids": ids},
            model=CollectionDetailsResponse,
            http_method="POST",
            auth_type="none",
        )
        return result.response
