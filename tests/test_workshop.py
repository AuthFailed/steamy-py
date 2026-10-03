"""Tests for ``WorkshopAPI`` (steam.workshop).

- ``get_details``: IPublishedFileService/GetDetails
- ``query_files`` and ``iter_query_files``: IPublishedFileService/QueryFiles
- ``get_published_file_details``: ISteamRemoteStorage/GetPublishedFileDetails

The two service methods send the API key when the client has one, else the
access token. The ISteamRemoteStorage method is a keyless POST whose inputs go
in a form body; it must never send a credential.

The fixtures are real Steam replies (descriptions trimmed, pages cut to a few
items): workshop_get_details.json holds a GetDetails item plus a not-found
item taken from another real reply, workshop_query_files.json two items of
one QueryFiles page with its real total and next_cursor, and
workshop_published_file_details.json a GetPublishedFileDetails reply with a
found and a not-found item.

The Milestone 2 methods are tested at the end of the file:

- ``get_user_files`` and ``iter_user_files``: IPublishedFileService/GetUserFiles
  (API key, else access token)
- ``subscribe`` and ``unsubscribe``: IPublishedFileService/Subscribe and
  Unsubscribe, POST writes that send only the access token
- ``get_collection_details``: ISteamRemoteStorage/GetCollectionDetails, a
  keyless POST

workshop_get_user_files.json is a real GetUserFiles reply published in
Shr1mpTop/my-steam-notes (docs/api-test-results-full.md); the source cuts it
off inside ``vote_data``, so the fixture ends the item there.
workshop_get_collection_details.json is the reply captured in FakeApate/pzsm
(internal/steam/testdata/collection_details.json), cut to the collection's
first three of 248 children.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    InvalidAppIDError,
    InvalidSteamIDError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
    SteamID,
)
from steamy_py.models.workshop import (
    CollectionDetails,
    CollectionDetailsList,
    EPublishedFileQueryType,
    EUCMListType,
    PublishedFileDetails,
    PublishedFileDetailsList,
    QueryFilesResult,
    RemoteStorageFileDetails,
    RemoteStorageFileDetailsList,
    UserFilesApp,
    UserFilesResult,
)
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

GET_DETAILS = "/IPublishedFileService/GetDetails/v1/"
QUERY_FILES = "/IPublishedFileService/QueryFiles/v1/"
REMOTE_STORAGE = "/ISteamRemoteStorage/GetPublishedFileDetails/v1/"

DETAILS: dict[str, Any] = load_fixture("workshop_get_details.json")
QUERY: dict[str, Any] = load_fixture("workshop_query_files.json")
REMOTE: dict[str, Any] = load_fixture("workshop_published_file_details.json")
EMPTY: dict[str, Any] = {"response": {}}

ITEM_ID = 2780180614  # found in workshop_get_details.json
MISSING_ID = 2047414260  # result 9 in workshop_get_details.json
OTHER_ID = 3464502292
QUERY_IDS = ["3464984971", "3464502292"]  # workshop_query_files.json
LEGACY_ID = 450814997  # found in workshop_published_file_details.json
LEGACY_MISSING_ID = 3325368063  # result 9 there
# A real next_cursor; its "+" must reach Steam percent-encoded, not as a space.
CURSOR = "AoJckcH+M3ey8Zdn"

DEFAULT_DETAILS_INPUTS = {
    "includetags": "0",
    "includeadditionalpreviews": "0",
    "includechildren": "0",
    "includekvtags": "0",
    "includevotes": "0",
    "short_description": "0",
    "includeforsaledata": "0",
    "includemetadata": "0",
    "language": "0",
    "strip_description_bbcode": "0",
    "includereactions": "0",
}

DEFAULT_QUERY_INPUTS = {
    "query_type": "0",
    "cursor": "*",
    "language": "0",
    "return_details": "1",
    "return_vote_data": "0",
    "return_tags": "0",
    "return_kv_tags": "0",
    "return_previews": "0",
    "return_children": "0",
    "return_short_description": "0",
    "return_for_sale_data": "0",
    "return_metadata": "0",
    "return_reactions": "0",
    "strip_description_bbcode": "0",
}

INVALID_IDS = [
    pytest.param([], id="empty-list"),
    pytest.param((), id="empty-tuple"),
    pytest.param(True, id="bool"),
    pytest.param([ITEM_ID, False], id="bool-in-list"),
    pytest.param(b"12", id="bytes"),
    pytest.param(0, id="zero"),
    pytest.param(-5, id="negative"),
    pytest.param(2**64, id="above-uint64"),
    pytest.param("18446744073709551616", id="above-uint64-str"),
    pytest.param("", id="empty-str"),
    pytest.param("abc", id="not-digits"),
    pytest.param("-5", id="negative-str"),
    pytest.param(" 42", id="whitespace"),
    pytest.param("4٢", id="non-ascii-digit"),
    pytest.param(1.5, id="float"),
    pytest.param(None, id="none"),
    pytest.param([ITEM_ID, None], id="none-in-list"),
]

INVALID_APP_IDS = [0, -1, True, 2**32, "440"]


@dataclass(frozen=True)
class Endpoint:
    """One ``WorkshopAPI`` request, called with realistic arguments."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    verb: str
    path: str
    reply: dict[str, Any]
    malformed: Any  # JSON that does not fit the method's model
    operation: str  # what the error message says failed

    def serve(self, fake_steam: FakeSteam, **reply: Any) -> None:
        """Register ``reply`` (default: the realistic one) for this method."""
        fake_steam.add(self.verb, self.path, **(reply or {"json": self.reply}))


ENDPOINTS = [
    Endpoint(
        "get_details",
        lambda steam: steam.workshop.get_details([ITEM_ID, MISSING_ID]),
        "GET",
        GET_DETAILS,
        DETAILS,
        {"response": {"publishedfiledetails": [{"tags": "Maps"}]}},
        "get workshop item details",
    ),
    Endpoint(
        "query_files",
        lambda steam: steam.workshop.query_files(appid=294100, numperpage=2),
        "GET",
        QUERY_FILES,
        QUERY,
        {"response": {"total": "many"}},
        "query workshop files",
    ),
    Endpoint(
        "get_published_file_details",
        lambda steam: steam.workshop.get_published_file_details(
            [LEGACY_ID, LEGACY_MISSING_ID]
        ),
        "POST",
        REMOTE_STORAGE,
        REMOTE,
        {"response": {"publishedfiledetails": {"publishedfileid": "1"}}},
        "get published file details",
    ),
]
SERVICE_ENDPOINTS = ENDPOINTS[:2]


def endpoint_params(endpoints: list[Endpoint]) -> Any:
    return pytest.mark.parametrize(
        "endpoint", [pytest.param(endpoint, id=endpoint.name) for endpoint in endpoints]
    )


def sent(pairs: Any) -> dict[str, str]:
    """``pairs`` (a query string or form body) as a dict, checking that no
    name was sent twice."""
    items = list(pairs.items())
    assert len({name for name, _ in items}) == len(items), items
    return dict(items)


def query_without_key(request: RecordedRequest) -> dict[str, str]:
    """The query string of ``request``, minus the API key."""
    inputs = sent(request.query)
    assert inputs.pop("key") == API_KEY
    assert "access_token" not in inputs
    return inputs


@pytest.fixture
async def token_only_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client that has an access token but no Web API key."""
    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as client:
        yield client


@pytest.fixture
async def anonymous_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client with no credential at all."""
    async with Steam(settings=settings) as client:
        yield client


# -- every method -------------------------------------------------------------


@endpoint_params(ENDPOINTS)
async def test_call_is_one_request_with_documented_verb_and_path(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [
        (endpoint.verb, endpoint.path)
    ]


@endpoint_params(ENDPOINTS)
async def test_http_500_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json={"error": "Internal Server Error"}, status=500)

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(steam)

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == 500
    assert len(fake_steam.requests) == 1


@endpoint_params(ENDPOINTS)
async def test_malformed_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json=endpoint.malformed)

    with pytest.raises(ResponseParsingError, match=f"Failed to {endpoint.operation}"):
        await endpoint.call(steam)


@endpoint_params(ENDPOINTS)
async def test_non_json_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, text="<html>Error</html>", content_type="text/html")

    with pytest.raises(ResponseParsingError, match="Invalid JSON response"):
        await endpoint.call(steam)


@endpoint_params(SERVICE_ENDPOINTS)
async def test_service_method_sends_api_key_when_client_has_both(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert fake_steam.last.params["key"] == API_KEY
    assert "access_token" not in fake_steam.last.params
    assert fake_steam.last.form == {}


@endpoint_params(SERVICE_ENDPOINTS)
async def test_service_method_sends_access_token_without_api_key(
    token_only_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(token_only_steam)

    assert fake_steam.last.params["access_token"] == ACCESS_TOKEN
    assert "key" not in fake_steam.last.params


@endpoint_params(SERVICE_ENDPOINTS)
async def test_service_method_without_credential_raises_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    with pytest.raises(AuthenticationError, match="API key or access token"):
        await endpoint.call(anonymous_steam)

    assert fake_steam.requests == []


# -- get_details ----------------------------------------------------------------


async def test_get_details_sends_ids_and_default_flags(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GET_DETAILS, json=DETAILS)

    await steam.workshop.get_details([ITEM_ID, str(OTHER_ID), MISSING_ID])

    assert query_without_key(fake_steam.last) == {
        "publishedfileids[0]": str(ITEM_ID),
        "publishedfileids[1]": str(OTHER_ID),
        "publishedfileids[2]": str(MISSING_ID),
        **DEFAULT_DETAILS_INPUTS,
    }


async def test_get_details_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GET_DETAILS, json=DETAILS)

    await steam.workshop.get_details(
        ITEM_ID,
        includetags=True,
        includeadditionalpreviews=True,
        includechildren=True,
        includekvtags=True,
        includevotes=True,
        short_description=True,
        includeforsaledata=True,
        includemetadata=True,
        language=7,
        return_playtime_stats=30,
        appid=281990,
        strip_description_bbcode=True,
        includereactions=True,
    )

    assert query_without_key(fake_steam.last) == {
        "publishedfileids[0]": str(ITEM_ID),
        "includetags": "1",
        "includeadditionalpreviews": "1",
        "includechildren": "1",
        "includekvtags": "1",
        "includevotes": "1",
        "short_description": "1",
        "includeforsaledata": "1",
        "includemetadata": "1",
        "language": "7",
        "return_playtime_stats": "30",
        "appid": "281990",
        "strip_description_bbcode": "1",
        "includereactions": "1",
    }


@pytest.mark.parametrize(
    ("ids", "expected"),
    [
        pytest.param(ITEM_ID, [str(ITEM_ID)], id="one-int"),
        pytest.param(str(ITEM_ID), [str(ITEM_ID)], id="one-str"),
        pytest.param("0042", ["42"], id="leading-zeros"),
        pytest.param(2**64 - 1, [str(2**64 - 1)], id="uint64-max"),
        pytest.param(
            (i for i in (ITEM_ID, OTHER_ID)),
            [str(ITEM_ID), str(OTHER_ID)],
            id="generator",
        ),
    ],
)
async def test_get_details_accepts_ids_as_int_or_str(
    steam: Steam, fake_steam: FakeSteam, ids: Any, expected: list[str]
) -> None:
    fake_steam.api("GET", GET_DETAILS, json=EMPTY)

    await steam.workshop.get_details(ids)

    sent_ids = [
        value
        for name, value in fake_steam.last.query.items()
        if name.startswith("publishedfileids")
    ]
    assert sent_ids == expected


@pytest.mark.parametrize("ids", INVALID_IDS)
async def test_get_details_rejects_invalid_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam, ids: Any
) -> None:
    with pytest.raises(ValueError, match="published file id"):
        await steam.workshop.get_details(ids)

    assert fake_steam.requests == []


@pytest.mark.parametrize("appid", INVALID_APP_IDS)
async def test_get_details_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appid: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.workshop.get_details(ITEM_ID, appid=appid)

    assert fake_steam.requests == []


async def test_get_details_parses_items(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", GET_DETAILS, json=DETAILS)

    result = await steam.workshop.get_details(
        [ITEM_ID, MISSING_ID],
        includetags=True,
        includeadditionalpreviews=True,
        includevotes=True,
    )

    assert isinstance(result, PublishedFileDetailsList)
    found, missing = result.publishedfiledetails
    assert isinstance(found, PublishedFileDetails)
    assert found.result == 1
    assert found.publishedfileid == str(ITEM_ID)
    assert found.creator == "76561198092064326"
    assert (found.creator_appid, found.consumer_appid) == (281990, 281990)
    assert found.title == "OUTDATED Cross Border Trade"
    assert found.app_name == "Stellaris"
    assert found.file_size == 261157
    assert found.preview_file_size == 240408
    assert found.hcontent_file == "9215042440569310672"
    assert found.banner == "76561197960265728"
    assert found.visibility == 3
    assert found.flags == 5632
    assert (found.time_created, found.time_updated) == (1647486579, 1730223116)
    assert (found.subscriptions, found.lifetime_subscriptions) == (25839, 78565)
    assert (found.favorited, found.lifetime_favorited) == (2473, 3167)
    assert (found.lifetime_playtime, found.lifetime_playtime_sessions) == (0, 0)
    assert found.views == 84577
    assert found.num_comments_public == 170
    assert found.can_subscribe and found.can_be_deleted and not found.banned
    assert found.revision_change_number == 31
    assert found.revision == 1
    assert found.ban_text_check_result == 5
    assert [(t.tag, t.display_name) for t in found.tags] == [
        ("Diplomacy", "Diplomacy"),
        ("Economy", "Economy"),
        ("Gameplay", "Gameplay"),
    ]
    assert found.vote_data.votes_up == 846
    assert found.vote_data.votes_down == 9
    assert found.vote_data.score == pytest.approx(0.93822, abs=1e-5)
    (preview,) = found.previews
    assert (preview.previewid, preview.sortorder, preview.size) == (
        "28788377",
        1,
        149495,
    )
    assert preview.filename == "Screenshot from 2022-08-26 11-13-02.png"
    assert found.children == found.kvtags == found.reactions == []

    assert missing.result == 9
    assert missing.publishedfileid == str(MISSING_ID)
    assert missing.title == ""
    assert missing.tags == []
    assert missing.vote_data.votes_up == 0


async def test_published_file_details_parses_optional_parts() -> None:
    # Parts the fixtures do not show, shaped as PublishedFileDetails in
    # SteamDatabase steam/steammessages_publishedfile.steamclient.proto:
    # uint64 counts arrive as strings, floats and uint32s as numbers.
    details = PublishedFileDetails.model_validate(
        {
            "children": [
                {"publishedfileid": "3342198659", "sortorder": 1, "file_type": 0}
            ],
            "kvtags": [{"key": "bis_size", "value": "129040219"}],
            "reactions": [{"reactionid": 7, "count": 1}],
            "playtime_stats": {"playtime_seconds": "7200", "num_sessions": "6"},
            "for_sale_data": {"is_for_sale": True, "estatus": 2},
            "available_revisions": [1, 6],
            "content_descriptorids": [1, 5],
            "author_snapshots": [{"timestamp": 1700000000, "manifestid": "42"}],
            "external_asset_id": "18446744073709551615",
        }
    )

    assert [(c.publishedfileid, c.sortorder) for c in details.children] == [
        ("3342198659", 1)
    ]
    assert [(kv.key, kv.value) for kv in details.kvtags] == [("bis_size", "129040219")]
    assert [(r.reactionid, r.count) for r in details.reactions] == [(7, 1)]
    assert details.playtime_stats.playtime_seconds == 7200
    assert details.playtime_stats.num_sessions == 6
    assert details.for_sale_data.is_for_sale is True
    assert details.for_sale_data.estatus == 2
    assert details.available_revisions == [1, 6]
    assert details.content_descriptorids == [1, 5]
    assert details.author_snapshots == [{"timestamp": 1700000000, "manifestid": "42"}]
    assert details.external_asset_id == "18446744073709551615"


async def test_get_details_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GET_DETAILS, json=EMPTY)

    result = await steam.workshop.get_details(ITEM_ID)

    assert result.publishedfiledetails == []


async def test_published_file_details_defaults_every_field() -> None:
    details = PublishedFileDetails.model_validate({})

    assert details.publishedfileid == ""
    assert details.file_size == 0
    assert details.tags == details.previews == details.children == []
    assert details.vote_data.score == 0.0
    assert details.for_sale_data.is_for_sale is False
    assert details.playtime_stats.num_sessions == 0
    assert details.author_snapshots == []


# -- query_files ------------------------------------------------------------------


async def test_query_files_sends_defaults_and_first_cursor(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY_FILES, json=QUERY)

    await steam.workshop.query_files()

    assert query_without_key(fake_steam.last) == DEFAULT_QUERY_INPUTS


async def test_query_files_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY_FILES, json=QUERY)

    await steam.workshop.query_files(
        EPublishedFileQueryType.RANKED_BY_TREND,
        appid=440,
        creator_appid=766,
        cursor=CURSOR,
        numperpage=50,
        requiredtags=["Maps", "Payload"],
        excludedtags="Halloween",
        match_all_tags=False,
        search_text="frost watch",
        filetype=0,
        child_publishedfileid=str(OTHER_ID),
        days=7,
        include_recent_votes_only=True,
        cache_max_age_seconds=60,
        language=7,
        totalonly=False,
        ids_only=False,
        return_details=False,
        return_vote_data=True,
        return_tags=True,
        return_kv_tags=True,
        return_previews=True,
        return_children=True,
        return_short_description=True,
        return_for_sale_data=True,
        return_metadata=True,
        return_playtime_stats=14,
        return_reactions=True,
        strip_description_bbcode=True,
    )

    assert query_without_key(fake_steam.last) == {
        "query_type": "3",
        "cursor": CURSOR,
        "numperpage": "50",
        "creator_appid": "766",
        "appid": "440",
        "requiredtags[0]": "Maps",
        "requiredtags[1]": "Payload",
        "excludedtags[0]": "Halloween",
        "match_all_tags": "0",
        "search_text": "frost watch",
        "filetype": "0",
        "child_publishedfileid": str(OTHER_ID),
        "days": "7",
        "include_recent_votes_only": "1",
        "cache_max_age_seconds": "60",
        "language": "7",
        "totalonly": "0",
        "ids_only": "0",
        "return_details": "0",
        "return_vote_data": "1",
        "return_tags": "1",
        "return_kv_tags": "1",
        "return_previews": "1",
        "return_children": "1",
        "return_short_description": "1",
        "return_for_sale_data": "1",
        "return_metadata": "1",
        "return_playtime_stats": "14",
        "return_reactions": "1",
        "strip_description_bbcode": "1",
    }


async def test_query_files_by_page_number_sends_no_cursor(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY_FILES, json=QUERY)

    await steam.workshop.query_files(appid=440, page=3)

    inputs = query_without_key(fake_steam.last)
    assert inputs["page"] == "3"
    assert "cursor" not in inputs


async def test_query_files_parses_page(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", QUERY_FILES, json=QUERY)

    result = await steam.workshop.query_files(appid=294100, numperpage=2)

    assert isinstance(result, QueryFilesResult)
    assert result.total == 42344
    assert result.next_cursor == CURSOR
    first, second = result.publishedfiledetails
    assert [first.publishedfileid, second.publishedfileid] == QUERY_IDS
    assert first.title == "Medieval Things: Geysers"
    assert first.app_name == "RimWorld"
    assert first.file_size == 1002248
    assert (first.subscriptions, first.views) == (137, 607)
    assert [t.tag for t in first.tags] == ["Mod", "1.5"]
    assert first.children == []
    assert second.title == "ABC body 2-简体中文"
    assert second.flags == 134223360
    assert second.maybe_inappropriate_sex is True
    assert second.content_descriptorids == [1, 5]
    assert second.num_children == 1
    assert [(c.publishedfileid, c.sortorder, c.file_type) for c in second.children] == [
        ("3342198659", 1, 0)
    ]
    assert second.tags == []


async def test_query_files_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY_FILES, json=EMPTY)

    result = await steam.workshop.query_files(appid=440, totalonly=True)

    assert result.total == 0
    assert result.publishedfiledetails == []
    assert result.next_cursor == ""


@pytest.mark.parametrize("field", ["appid", "creator_appid"])
@pytest.mark.parametrize("appid", INVALID_APP_IDS)
async def test_query_files_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, field: str, appid: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.workshop.query_files(**{field: appid})

    assert fake_steam.requests == []


@pytest.mark.parametrize("child", [0, True, "abc", -1, 2**64])
async def test_query_files_rejects_invalid_child_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, child: Any
) -> None:
    with pytest.raises(ValueError, match="published file id"):
        await steam.workshop.query_files(child_publishedfileid=child)

    assert fake_steam.requests == []


# -- iter_query_files ---------------------------------------------------------------


def query_page(ids: list[int], next_cursor: str | None) -> dict[str, Any]:
    """A QueryFiles reply with ``ids`` (as returned with ids_only)."""
    page: dict[str, Any] = {
        "total": 5,
        "publishedfiledetails": [
            {"result": 1, "publishedfileid": str(i), "language": 0} for i in ids
        ],
    }
    if next_cursor is not None:
        page["next_cursor"] = next_cursor
    return {"response": page}


def sent_cursors(fake_steam: FakeSteam) -> list[str]:
    return [request.params["cursor"] for request in fake_steam.requests]


def fail_further_pages(fake_steam: FakeSteam) -> None:
    """Answer any page after the queued ones with HTTP 500, so an iterator
    that misses its stop condition fails instead of looping forever."""
    fake_steam.api("GET", QUERY_FILES, json={"error": "too many pages"}, status=500)


async def test_iter_query_files_follows_cursor_until_it_repeats(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY_FILES, json=query_page([11, 12], CURSOR))
    fake_steam.api("GET", QUERY_FILES, json=query_page([13, 14], "c2"))
    fake_steam.api("GET", QUERY_FILES, json=query_page([15], "c2"))
    fail_further_pages(fake_steam)

    items = [
        item.publishedfileid
        async for item in steam.workshop.iter_query_files(
            EPublishedFileQueryType.RANKED_BY_PUBLICATION_DATE,
            numperpage=2,
            appid=440,
            ids_only=True,
        )
    ]

    assert items == ["11", "12", "13", "14", "15"]
    assert sent_cursors(fake_steam) == ["*", CURSOR, "c2"]
    for request in fake_steam.requests:
        assert request.params["query_type"] == "1"
        assert request.params["numperpage"] == "2"
        assert request.params["appid"] == "440"
        assert request.params["ids_only"] == "1"
        assert "page" not in request.params


async def test_iter_query_files_stops_at_an_empty_page(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY_FILES, json=query_page([11, 12], "c1"))
    fake_steam.api("GET", QUERY_FILES, json=query_page([], "c2"))
    fail_further_pages(fake_steam)

    items = [item async for item in steam.workshop.iter_query_files(appid=440)]

    assert [item.publishedfileid for item in items] == ["11", "12"]
    assert sent_cursors(fake_steam) == ["*", "c1"]
    assert fake_steam.last.params["numperpage"] == "100"


async def test_iter_query_files_stops_without_next_cursor(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY_FILES, json=query_page([11], None))
    fail_further_pages(fake_steam)

    items = [item async for item in steam.workshop.iter_query_files(appid=440)]

    assert [item.publishedfileid for item in items] == ["11"]
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize("paging", [{"page": 2}, {"cursor": CURSOR}])
async def test_iter_query_files_rejects_page_and_cursor(
    steam: Steam, fake_steam: FakeSteam, paging: dict[str, Any]
) -> None:
    with pytest.raises(TypeError, match="page and cursor"):
        async for _ in steam.workshop.iter_query_files(appid=440, **paging):
            pass

    assert fake_steam.requests == []


# -- get_published_file_details -----------------------------------------------------


async def test_get_published_file_details_posts_form_without_credential(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", REMOTE_STORAGE, json=REMOTE)

    await steam.workshop.get_published_file_details([LEGACY_ID, str(LEGACY_MISSING_ID)])

    request = fake_steam.last
    assert sent(request.form) == {
        "itemcount": "2",
        "publishedfileids[0]": str(LEGACY_ID),
        "publishedfileids[1]": str(LEGACY_MISSING_ID),
    }
    assert sent(request.query) == {}
    assert API_KEY.encode() not in request.body
    assert ACCESS_TOKEN.encode() not in request.body
    assert "Cookie" not in request.headers


async def test_get_published_file_details_needs_no_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", REMOTE_STORAGE, json=REMOTE)

    result = await anonymous_steam.workshop.get_published_file_details(LEGACY_ID)

    assert sent(fake_steam.last.form) == {
        "itemcount": "1",
        "publishedfileids[0]": str(LEGACY_ID),
    }
    assert result.resultcount == 2


async def test_get_published_file_details_parses_items(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", REMOTE_STORAGE, json=REMOTE)

    result = await steam.workshop.get_published_file_details(
        [LEGACY_ID, LEGACY_MISSING_ID]
    )

    assert isinstance(result, RemoteStorageFileDetailsList)
    assert (result.result, result.resultcount) == (1, 2)
    found, missing = result.publishedfiledetails
    assert isinstance(found, RemoteStorageFileDetails)
    assert found.result == 1
    assert found.publishedfileid == str(LEGACY_ID)
    assert found.creator == "76561198198595822"
    assert (found.creator_app_id, found.consumer_app_id) == (107410, 107410)
    assert found.title == "CBA_A3"
    assert found.description.startswith("[h1][b]CBA: Community Based Addons")
    assert found.file_size == 4840892
    assert found.hcontent_file == "8288142167768285117"
    assert found.hcontent_preview == "1014940825593906790"
    assert (found.time_created, found.time_updated) == (1432827434, 1775056591)
    assert found.visibility == 0
    assert found.banned is False
    assert (found.subscriptions, found.lifetime_subscriptions) == (3118457, 4250143)
    assert (found.favorited, found.lifetime_favorited) == (65432, 71005)
    assert found.views == 2040262
    assert [tag.tag for tag in found.tags] == ["Mod"]

    assert missing.result == 9
    assert missing.publishedfileid == str(LEGACY_MISSING_ID)
    assert missing.title == ""
    assert missing.file_size == 0
    assert missing.tags == []


@pytest.mark.parametrize("file_size", [4213879, "4213879"])
async def test_get_published_file_details_reads_file_size_as_int_or_str(
    steam: Steam, fake_steam: FakeSteam, file_size: int | str
) -> None:
    item = {"publishedfileid": str(LEGACY_ID), "result": 1, "file_size": file_size}
    reply = {
        "response": {"result": 1, "resultcount": 1, "publishedfiledetails": [item]}
    }
    fake_steam.api("POST", REMOTE_STORAGE, json=reply)

    result = await steam.workshop.get_published_file_details(LEGACY_ID)

    assert result.publishedfiledetails[0].file_size == 4213879


async def test_get_published_file_details_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", REMOTE_STORAGE, json=EMPTY)

    result = await steam.workshop.get_published_file_details(LEGACY_ID)

    assert result.result == 0
    assert result.resultcount == 0
    assert result.publishedfiledetails == []


@pytest.mark.parametrize("ids", INVALID_IDS)
async def test_get_published_file_details_rejects_invalid_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam, ids: Any
) -> None:
    with pytest.raises(ValueError, match="published file id"):
        await steam.workshop.get_published_file_details(ids)

    assert fake_steam.requests == []


# == Milestone 2 ======================================================================

USER_FILES = "/IPublishedFileService/GetUserFiles/v1/"
SUBSCRIBE = "/IPublishedFileService/Subscribe/v1/"
UNSUBSCRIBE = "/IPublishedFileService/Unsubscribe/v1/"
COLLECTIONS = "/ISteamRemoteStorage/GetCollectionDetails/v1/"

USER_FILES_REPLY: dict[str, Any] = load_fixture("workshop_get_user_files.json")
COLLECTION_REPLY: dict[str, Any] = load_fixture("workshop_get_collection_details.json")

USER_STEAMID = "76561198367786896"  # creator in workshop_get_user_files.json
USER_ITEM_ID = "2863985395"  # its item
WALLPAPER_ENGINE = 431960
COLLECTION_ID = 3707778024  # workshop_get_collection_details.json
COLLECTION_CHILDREN = ["3005903549", "3026723485", "2937786633"]

DEFAULT_USER_FILES_INPUTS = {
    "steamid": USER_STEAMID,
    "language": "0",
    # Steam's proto defaults: on for vote data, kv tags and short descriptions.
    "return_vote_data": "1",
    "return_tags": "0",
    "return_kv_tags": "1",
    "return_previews": "0",
    "return_children": "0",
    "return_short_description": "1",
    "return_for_sale_data": "0",
    "return_metadata": "0",
    "return_reactions": "0",
    "return_apps": "0",
}

M2_ENDPOINTS = [
    Endpoint(
        "get_user_files",
        lambda steam: steam.workshop.get_user_files(
            USER_STEAMID, appid=WALLPAPER_ENGINE
        ),
        "GET",
        USER_FILES,
        USER_FILES_REPLY,
        {"response": {"total": "many"}},
        "get user workshop files",
    ),
    Endpoint(
        "subscribe",
        lambda steam: steam.workshop.subscribe(ITEM_ID),
        "POST",
        SUBSCRIBE,
        EMPTY,
        {"response": []},
        "subscribe to workshop item",
    ),
    Endpoint(
        "unsubscribe",
        lambda steam: steam.workshop.unsubscribe(ITEM_ID),
        "POST",
        UNSUBSCRIBE,
        EMPTY,
        {"response": "ok"},
        "unsubscribe from workshop item",
    ),
    Endpoint(
        "get_collection_details",
        lambda steam: steam.workshop.get_collection_details(COLLECTION_ID),
        "POST",
        COLLECTIONS,
        COLLECTION_REPLY,
        {"response": {"collectiondetails": {"publishedfileid": "1"}}},
        "get collection details",
    ),
]
SUBSCRIPTION_ENDPOINTS = M2_ENDPOINTS[1:3]


@pytest.fixture
async def key_only_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client that has a Web API key but no access token."""
    async with Steam(api_key=API_KEY, settings=settings) as client:
        yield client


# -- every Milestone 2 method -----------------------------------------------------


@endpoint_params(M2_ENDPOINTS)
async def test_m2_call_is_one_request_with_documented_verb_and_path(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [
        (endpoint.verb, endpoint.path)
    ]


@endpoint_params(M2_ENDPOINTS)
async def test_m2_http_500_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json={"error": "Internal Server Error"}, status=500)

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(steam)

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@endpoint_params(M2_ENDPOINTS)
async def test_m2_malformed_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json=endpoint.malformed)

    with pytest.raises(ResponseParsingError, match=f"Failed to {endpoint.operation}"):
        await endpoint.call(steam)


@endpoint_params(M2_ENDPOINTS)
async def test_m2_body_that_is_not_an_object_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json=[])

    with pytest.raises(ResponseParsingError, match=f"Failed to {endpoint.operation}"):
        await endpoint.call(steam)


@endpoint_params(M2_ENDPOINTS)
async def test_m2_non_json_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, text="<html>Error</html>", content_type="text/html")

    with pytest.raises(ResponseParsingError, match="Invalid JSON response"):
        await endpoint.call(steam)


# -- get_user_files ------------------------------------------------------------------


async def test_get_user_files_sends_api_key_when_client_has_both(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", USER_FILES, json=USER_FILES_REPLY)

    await steam.workshop.get_user_files(USER_STEAMID)

    assert query_without_key(fake_steam.last) == DEFAULT_USER_FILES_INPUTS
    assert fake_steam.last.form == {}


async def test_get_user_files_sends_access_token_without_api_key(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", USER_FILES, json=USER_FILES_REPLY)

    await token_only_steam.workshop.get_user_files(USER_STEAMID)

    inputs = sent(fake_steam.last.query)
    assert inputs.pop("access_token") == ACCESS_TOKEN
    assert inputs == DEFAULT_USER_FILES_INPUTS


async def test_get_user_files_without_credential_raises_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", USER_FILES, json=USER_FILES_REPLY)

    with pytest.raises(AuthenticationError, match="API key or access token"):
        await anonymous_steam.workshop.get_user_files(USER_STEAMID)

    assert fake_steam.requests == []


async def test_get_user_files_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", USER_FILES, json=USER_FILES_REPLY)

    await steam.workshop.get_user_files(
        int(USER_STEAMID),
        appid=WALLPAPER_ENGINE,
        page=2,
        numperpage=30,
        type="mysubscriptions",
        sortmethod="lastupdated",
        privacy=8,
        requiredtags=["Wallpaper", "Video"],
        excludedtags="Mature",
        filetype=0,
        creator_appid=WALLPAPER_ENGINE,
        match_cloud_filename="scene.pkg",
        cache_max_age_seconds=60,
        language=6,
        totalonly=False,
        ids_only=False,
        return_vote_data=False,
        return_tags=True,
        return_kv_tags=False,
        return_previews=True,
        return_children=True,
        return_short_description=False,
        return_for_sale_data=True,
        return_metadata=True,
        return_playtime_stats=7,
        return_reactions=True,
        return_apps=True,
        strip_description_bbcode=True,
    )

    assert query_without_key(fake_steam.last) == {
        "steamid": USER_STEAMID,
        "appid": str(WALLPAPER_ENGINE),
        "page": "2",
        "numperpage": "30",
        "type": "mysubscriptions",
        "sortmethod": "lastupdated",
        "privacy": "8",
        "requiredtags[0]": "Wallpaper",
        "requiredtags[1]": "Video",
        "excludedtags[0]": "Mature",
        "filetype": "0",
        "creator_appid": str(WALLPAPER_ENGINE),
        "match_cloud_filename": "scene.pkg",
        "cache_max_age_seconds": "60",
        "language": "6",
        "totalonly": "0",
        "ids_only": "0",
        "return_vote_data": "0",
        "return_tags": "1",
        "return_kv_tags": "0",
        "return_previews": "1",
        "return_children": "1",
        "return_short_description": "0",
        "return_for_sale_data": "1",
        "return_metadata": "1",
        "return_playtime_stats": "7",
        "return_reactions": "1",
        "return_apps": "1",
        "strip_description_bbcode": "1",
    }


@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param(int(USER_STEAMID), id="int"),
        pytest.param(USER_STEAMID, id="str"),
        pytest.param(SteamID(USER_STEAMID), id="SteamID"),
    ],
)
async def test_get_user_files_accepts_steamid_as_int_str_or_steamid(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    fake_steam.api("GET", USER_FILES, json=EMPTY)

    await steam.workshop.get_user_files(steamid)

    assert fake_steam.last.params["steamid"] == USER_STEAMID


@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param("", id="empty"),
        pytest.param("gabelogannewell", id="vanity-name"),
        pytest.param(22202, id="account-id"),
        pytest.param("103582791429521408", id="group-id"),
        pytest.param(True, id="bool"),
        pytest.param(b"76561198367786896", id="bytes"),
    ],
)
async def test_get_user_files_rejects_invalid_steamid_before_any_request(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    with pytest.raises(InvalidSteamIDError):
        await steam.workshop.get_user_files(steamid)

    assert fake_steam.requests == []


@pytest.mark.parametrize("field", ["appid", "creator_appid"])
@pytest.mark.parametrize("appid", INVALID_APP_IDS)
async def test_get_user_files_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, field: str, appid: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.workshop.get_user_files(USER_STEAMID, **{field: appid})

    assert fake_steam.requests == []


async def test_get_user_files_parses_page(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", USER_FILES, json=USER_FILES_REPLY)

    result = await steam.workshop.get_user_files(USER_STEAMID, return_tags=True)

    assert isinstance(result, UserFilesResult)
    assert (result.total, result.startindex) == (9, 1)
    assert result.apps == []
    (item,) = result.publishedfiledetails
    assert isinstance(item, PublishedFileDetails)
    assert item.result == 1
    assert item.publishedfileid == USER_ITEM_ID
    assert item.creator == USER_STEAMID
    assert (item.creator_appid, item.consumer_appid) == (431960, 431960)
    assert item.app_name == "Wallpaper Engine"
    # The real title and description use mathematical Fraktur letters,
    # which must come through unchanged.
    assert item.title.startswith("天国拯救高燃混剪\uff1a\U0001d576")
    assert len(item.title) == 20
    assert item.short_description.endswith("!!")
    assert item.file_description == ""
    # uint64 sizes and counts arrive as strings.
    assert (item.file_size, item.preview_file_size) == (523447204, 342785)
    assert (item.lifetime_playtime, item.lifetime_playtime_sessions) == (0, 0)
    assert item.hcontent_file == "7162398792635874947"
    assert (item.time_created, item.time_updated) == (1663401266, 1663406565)
    assert (item.subscriptions, item.lifetime_subscriptions) == (248, 923)
    assert (item.favorited, item.views) == (26, 80)
    assert item.can_be_deleted and item.can_subscribe and not item.banned
    assert [tag.tag for tag in item.tags] == [
        "Wallpaper",
        "Video",
        "Medieval",
        "1920 x 1080",
        "Everyone",
    ]
    assert [(kv.key, kv.value) for kv in item.kvtags][:3] == [
        ("Width", "1920"),
        ("Height", "1080"),
        ("version", "20000100000032"),
    ]
    assert item.vote_data.score == pytest.approx(0.5614035129)


async def test_get_user_files_parses_apps(steam: Steam, fake_steam: FakeSteam) -> None:
    # Shaped as CPublishedFile_GetUserFiles_Response_App: fields at their
    # default (shortcutid 0, private false) are left out.
    body = {
        "response": {
            "total": 1,
            "startindex": 1,
            "publishedfiledetails": [{"result": 1, "publishedfileid": USER_ITEM_ID}],
            "apps": [
                {"appid": WALLPAPER_ENGINE, "name": "Wallpaper Engine"},
                {"appid": 7, "name": "Hidden", "shortcutid": 3, "private": True},
            ],
        }
    }
    fake_steam.api("GET", USER_FILES, json=body)

    result = await steam.workshop.get_user_files(USER_STEAMID, return_apps=True)

    assert result.apps == [
        UserFilesApp(appid=WALLPAPER_ENGINE, name="Wallpaper Engine"),
        UserFilesApp(appid=7, name="Hidden", shortcutid=3, private=True),
    ]


async def test_get_user_files_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # A user without items: protobuf leaves out every field.
    fake_steam.api("GET", USER_FILES, json=EMPTY)

    result = await steam.workshop.get_user_files(USER_STEAMID)

    assert result == UserFilesResult()
    assert (result.total, result.startindex) == (0, 0)
    assert result.publishedfiledetails == result.apps == []


# -- iter_user_files ---------------------------------------------------------------


def user_page(ids: list[int], total: int, startindex: int) -> dict[str, Any]:
    """A GetUserFiles reply with ``ids`` (as returned with ids_only)."""
    page: dict[str, Any] = {"total": total}
    if ids:
        page["startindex"] = startindex
        page["publishedfiledetails"] = [
            {"result": 1, "publishedfileid": str(i)} for i in ids
        ]
    return {"response": page}


def sent_pages(fake_steam: FakeSteam) -> list[str]:
    return [request.params["page"] for request in fake_steam.requests]


def fail_further_user_pages(fake_steam: FakeSteam) -> None:
    """Answer any page after the queued ones with HTTP 500, so an iterator
    that misses its stop condition fails instead of looping forever."""
    fake_steam.api("GET", USER_FILES, json={"error": "too many pages"}, status=500)


async def test_iter_user_files_pages_until_total(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", USER_FILES, json=user_page([11, 12], 5, 1))
    fake_steam.api("GET", USER_FILES, json=user_page([13, 14], 5, 3))
    fake_steam.api("GET", USER_FILES, json=user_page([15], 5, 5))
    fail_further_user_pages(fake_steam)

    items = [
        item.publishedfileid
        async for item in steam.workshop.iter_user_files(
            USER_STEAMID,
            numperpage=2,
            appid=WALLPAPER_ENGINE,
            type="mysubscriptions",
            ids_only=True,
        )
    ]

    assert items == ["11", "12", "13", "14", "15"]
    assert sent_pages(fake_steam) == ["1", "2", "3"]
    for request in fake_steam.requests:
        assert request.params["steamid"] == USER_STEAMID
        assert request.params["numperpage"] == "2"
        assert request.params["appid"] == str(WALLPAPER_ENGINE)
        assert request.params["type"] == "mysubscriptions"
        assert request.params["ids_only"] == "1"


async def test_iter_user_files_stops_at_an_empty_page(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # total says more items exist, but the next page is empty.
    fake_steam.api("GET", USER_FILES, json=user_page([11, 12], 9, 1))
    fake_steam.api("GET", USER_FILES, json=user_page([], 9, 0))
    fail_further_user_pages(fake_steam)

    items = [item async for item in steam.workshop.iter_user_files(USER_STEAMID)]

    assert [item.publishedfileid for item in items] == ["11", "12"]
    assert sent_pages(fake_steam) == ["1", "2"]
    assert fake_steam.last.params["numperpage"] == "50"


async def test_iter_user_files_of_user_without_items_makes_one_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", USER_FILES, json=EMPTY)
    fail_further_user_pages(fake_steam)

    items = [item async for item in steam.workshop.iter_user_files(USER_STEAMID)]

    assert items == []
    assert len(fake_steam.requests) == 1


async def test_iter_user_files_raises_when_a_page_skips_items(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Steam honoured only 2 of the 3 items per page asked for: page 2 starts
    # at item 4, so item 3 would be skipped.
    fake_steam.api("GET", USER_FILES, json=user_page([11, 12], 9, 1))
    fake_steam.api("GET", USER_FILES, json=user_page([14, 15], 9, 4))
    fail_further_user_pages(fake_steam)

    seen: list[str] = []
    with pytest.raises(SteamAPIError, match="from item 4, expected item 3"):
        async for item in steam.workshop.iter_user_files(USER_STEAMID, numperpage=3):
            seen.append(item.publishedfileid)

    assert seen == ["11", "12"]
    assert len(fake_steam.requests) == 2


async def test_iter_user_files_rejects_page(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(TypeError, match="omit page"):
        async for _ in steam.workshop.iter_user_files(USER_STEAMID, page=2):
            pass

    assert fake_steam.requests == []


async def test_iter_user_files_rejects_invalid_steamid_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(InvalidSteamIDError):
        async for _ in steam.workshop.iter_user_files("gabelogannewell"):
            pass

    assert fake_steam.requests == []


# -- subscribe / unsubscribe --------------------------------------------------------


async def test_subscribe_posts_item_and_token_in_form_body(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", SUBSCRIBE, json=EMPTY)

    result = await steam.workshop.subscribe(ITEM_ID)

    request = fake_steam.last
    assert sent(request.form) == {
        "publishedfileid": str(ITEM_ID),
        "list_type": "1",
        "notify_client": "0",
        "include_dependencies": "0",
        "access_token": ACCESS_TOKEN,
    }
    assert sent(request.query) == {}
    assert API_KEY.encode() not in request.body
    assert "Cookie" not in request.headers
    assert result is None


async def test_subscribe_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", SUBSCRIBE, json=EMPTY)

    await steam.workshop.subscribe(
        str(ITEM_ID),
        list_type=EUCMListType.FAVORITES,
        appid=281990,
        notify_client=True,
        include_dependencies=True,
    )

    assert sent(fake_steam.last.form) == {
        "publishedfileid": str(ITEM_ID),
        "list_type": "2",
        "appid": "281990",
        "notify_client": "1",
        "include_dependencies": "1",
        "access_token": ACCESS_TOKEN,
    }


async def test_unsubscribe_posts_item_and_token_in_form_body(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", UNSUBSCRIBE, json=EMPTY)

    result = await steam.workshop.unsubscribe(ITEM_ID)

    request = fake_steam.last
    assert sent(request.form) == {
        "publishedfileid": str(ITEM_ID),
        "list_type": "1",
        "notify_client": "0",
        "access_token": ACCESS_TOKEN,
    }
    assert sent(request.query) == {}
    assert API_KEY.encode() not in request.body
    assert result is None


async def test_unsubscribe_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", UNSUBSCRIBE, json=EMPTY)

    await steam.workshop.unsubscribe(
        str(ITEM_ID),
        list_type=EUCMListType.FOLLOWED,
        appid=281990,
        notify_client=True,
    )

    assert sent(fake_steam.last.form) == {
        "publishedfileid": str(ITEM_ID),
        "list_type": "6",
        "appid": "281990",
        "notify_client": "1",
        "access_token": ACCESS_TOKEN,
    }


def test_eucm_list_type_values() -> None:
    # OpenSteamworks enums.h and opensteamworks enums.steamd agree on these.
    assert {member.name: member.value for member in EUCMListType} == {
        "SUBSCRIBED": 1,
        "FAVORITES": 2,
        "PLAYED": 3,
        "COMPLETED": 4,
        "SHORTCUT_FAVORITES": 5,
        "FOLLOWED": 6,
    }


@endpoint_params(SUBSCRIPTION_ENDPOINTS)
async def test_subscription_works_with_only_an_access_token(
    token_only_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(token_only_steam)

    assert sent(fake_steam.last.form)["access_token"] == ACCESS_TOKEN


@endpoint_params(SUBSCRIPTION_ENDPOINTS)
async def test_subscription_needs_the_access_token_not_the_key(
    key_only_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await endpoint.call(key_only_steam)

    assert fake_steam.requests == []


@endpoint_params(SUBSCRIPTION_ENDPOINTS)
async def test_subscription_without_credential_raises_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    with pytest.raises(AuthenticationError):
        await endpoint.call(anonymous_steam)

    assert fake_steam.requests == []


@endpoint_params(SUBSCRIPTION_ENDPOINTS)
async def test_subscription_ignores_a_missing_response_object(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json={})

    assert await endpoint.call(steam) is None


@pytest.mark.parametrize(
    ("eresult", "error"),
    [
        pytest.param("9", SteamAPIError, id="file-not-found"),
        pytest.param("15", AuthenticationError, id="access-denied"),
    ],
)
@endpoint_params(SUBSCRIPTION_ENDPOINTS)
async def test_subscription_refused_by_steam_raises_with_eresult(
    steam: Steam,
    fake_steam: FakeSteam,
    endpoint: Endpoint,
    eresult: str,
    error: type[SteamAPIError],
) -> None:
    endpoint.serve(fake_steam, json=EMPTY, headers={"x-eresult": eresult})

    with pytest.raises(error) as excinfo:
        await endpoint.call(steam)

    assert type(excinfo.value) is error
    assert excinfo.value.eresult == int(eresult)
    assert ACCESS_TOKEN not in str(excinfo.value)
    # A POST that Steam refused is not repeated.
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    ("method", "path"), [("subscribe", SUBSCRIBE), ("unsubscribe", UNSUBSCRIBE)]
)
@pytest.mark.parametrize("ids", INVALID_IDS)
async def test_subscription_rejects_invalid_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, method: str, path: str, ids: Any
) -> None:
    fake_steam.api("POST", path, json=EMPTY)

    with pytest.raises(ValueError, match="published file id"):
        await getattr(steam.workshop, method)(ids)

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    ("method", "path"), [("subscribe", SUBSCRIBE), ("unsubscribe", UNSUBSCRIBE)]
)
@pytest.mark.parametrize("appid", INVALID_APP_IDS)
async def test_subscription_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, method: str, path: str, appid: Any
) -> None:
    fake_steam.api("POST", path, json=EMPTY)

    with pytest.raises(InvalidAppIDError):
        await getattr(steam.workshop, method)(ITEM_ID, appid=appid)

    assert fake_steam.requests == []


# -- get_collection_details ---------------------------------------------------------


async def test_get_collection_details_posts_form_without_credential(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", COLLECTIONS, json=COLLECTION_REPLY)

    await steam.workshop.get_collection_details([COLLECTION_ID, str(ITEM_ID)])

    request = fake_steam.last
    assert sent(request.form) == {
        "collectioncount": "2",
        "publishedfileids[0]": str(COLLECTION_ID),
        "publishedfileids[1]": str(ITEM_ID),
    }
    assert sent(request.query) == {}
    assert API_KEY.encode() not in request.body
    assert ACCESS_TOKEN.encode() not in request.body
    assert "Cookie" not in request.headers


async def test_get_collection_details_needs_no_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", COLLECTIONS, json=COLLECTION_REPLY)

    result = await anonymous_steam.workshop.get_collection_details(str(COLLECTION_ID))

    assert sent(fake_steam.last.form) == {
        "collectioncount": "1",
        "publishedfileids[0]": str(COLLECTION_ID),
    }
    assert result.resultcount == 1


async def test_get_collection_details_parses_collection(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", COLLECTIONS, json=COLLECTION_REPLY)

    result = await steam.workshop.get_collection_details(COLLECTION_ID)

    assert isinstance(result, CollectionDetailsList)
    assert (result.result, result.resultcount) == (1, 1)
    (collection,) = result.collectiondetails
    assert isinstance(collection, CollectionDetails)
    assert (collection.publishedfileid, collection.result) == (str(COLLECTION_ID), 1)
    assert [c.publishedfileid for c in collection.children] == COLLECTION_CHILDREN
    assert [c.sortorder for c in collection.children] == [0, 1, 2]
    assert [c.filetype for c in collection.children] == [0, 0, 0]


async def test_get_collection_details_parses_a_collection_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Shaped as the not-found entries of ISteamRemoteStorage's
    # GetPublishedFileDetails: only the id and an EResult other than 1.
    reply = {
        "response": {
            "result": 1,
            "resultcount": 2,
            "collectiondetails": [
                COLLECTION_REPLY["response"]["collectiondetails"][0],
                {"publishedfileid": str(MISSING_ID), "result": 9},
            ],
        }
    }
    fake_steam.api("POST", COLLECTIONS, json=reply)

    result = await steam.workshop.get_collection_details([COLLECTION_ID, MISSING_ID])

    found, missing = result.collectiondetails
    assert len(found.children) == 3
    assert (missing.publishedfileid, missing.result) == (str(MISSING_ID), 9)
    assert missing.children == []


async def test_get_collection_details_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", COLLECTIONS, json=EMPTY)

    result = await steam.workshop.get_collection_details(COLLECTION_ID)

    assert result == CollectionDetailsList()
    assert result.collectiondetails == []


@pytest.mark.parametrize("ids", INVALID_IDS)
async def test_get_collection_details_rejects_invalid_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam, ids: Any
) -> None:
    with pytest.raises(ValueError, match="published file id"):
        await steam.workshop.get_collection_details(ids)

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    "ids",
    [
        pytest.param(bytearray(b"12"), id="bytearray"),
        pytest.param(memoryview(b"12"), id="memoryview"),
    ],
)
async def test_get_collection_details_rejects_byte_buffers_before_any_request(
    steam: Steam, fake_steam: FakeSteam, ids: Any
) -> None:
    # Iterating a byte buffer gives ints (49, 50), which would pass as ids.
    with pytest.raises(ValueError, match="published file id"):
        await steam.workshop.get_collection_details(ids)

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda steam, ids: steam.workshop.get_details(ids), id="get_details"
        ),
        pytest.param(
            lambda steam, ids: steam.workshop.get_published_file_details(ids),
            id="get_published_file_details",
        ),
        pytest.param(
            lambda steam, ids: steam.workshop.get_collection_details(ids),
            id="get_collection_details",
        ),
    ],
)
@pytest.mark.parametrize(
    "ids", [bytearray(b"12"), memoryview(b"12")], ids=["bytearray", "memoryview"]
)
async def test_byte_buffers_are_never_read_as_published_file_ids(
    steam: Steam, fake_steam: FakeSteam, call: Any, ids: Any
) -> None:
    with pytest.raises(ValueError, match="Invalid published file id"):
        await call(steam, ids)

    assert fake_steam.requests == []


@pytest.mark.parametrize("tags", [b"Maps", bytearray(b"Maps")])
async def test_byte_tags_are_rejected(
    steam: Steam, fake_steam: FakeSteam, tags: Any
) -> None:
    with pytest.raises(TypeError, match="Tags must be str"):
        await steam.workshop.query_files(appid=440, requiredtags=tags)

    assert fake_steam.requests == []
