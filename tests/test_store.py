"""Tests for the store items, search, charts, tags, reviews and package methods
of ``steam.store`` (app details and the app list are in ``tests/test_game.py``).

Most of them need no credential, so none may be sent; ``get_dlc_for_apps`` and
``get_user_game_interest_state`` are about the signed-in user and need the
access token. Service methods with nested inputs send one ``input_json``
parameter.
"""

from __future__ import annotations

import asyncio
import json
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
from steamy_py.models.store import (
    AppDLCList,
    AppReview,
    AppReviews,
    CommunityApp,
    DiscoveryQueueState,
    DLCForApps,
    EPlaytestStatus,
    ESteamDeckCompatibilityCategory,
    EStoreAppType,
    EStoreCategoryType,
    EStoreDiscoveryQueueType,
    EStoreItemType,
    EUserReviewScore,
    GamesByConcurrentPlayers,
    ItemsToFeature,
    MostPlayedGames,
    PackageDetails,
    SearchSuggestions,
    StoreCategory,
    StoreDLCData,
    StoreItem,
    StoreItemID,
    StoreItems,
    StoreQueryResult,
    StoreSearchResult,
    StoreTag,
    TagList,
    UserGameInterestState,
    WeeklyTopSellers,
)
from tests.conftest import make_settings
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    STORE_PREFIX,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

GET_ITEMS = "/IStoreBrowseService/GetItems/v1/"
SEARCH_SUGGESTIONS = "/IStoreQueryService/SearchSuggestions/v1/"
STORE_SEARCH = "/storesearch/"

ITEMS: dict[str, Any] = load_fixture("store_get_items.json")
SUGGESTIONS: dict[str, Any] = load_fixture("store_search_suggestions.json")
SEARCH: dict[str, Any] = load_fixture("store_store_search.json")
EMPTY: dict[str, Any] = {"response": {}}

US_ENGLISH = {"language": "english", "country_code": "US", "steam_realm": 1}


@dataclass(frozen=True)
class Endpoint:
    """One keyless store method, called with realistic arguments."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    path: str  # as the fake server sees it
    reply: Any
    malformed: Any  # JSON that does not fit the method's model
    operation: str  # what the error message says failed

    def serve(self, fake_steam: FakeSteam, **reply: Any) -> None:
        """Register ``reply`` (default: the realistic one) for this method."""
        reply = reply or {"json": self.reply}
        fake_steam.add("GET", self.path, **reply)


ENDPOINTS = [
    Endpoint(
        "get_items",
        lambda steam: steam.store.get_items([620, 440]),
        GET_ITEMS,
        ITEMS,
        {"response": {"store_items": 1}},
        "get store items",
    ),
    Endpoint(
        "search_suggestions",
        lambda steam: steam.store.search_suggestions("portal"),
        SEARCH_SUGGESTIONS,
        SUGGESTIONS,
        {"response": {"ids": [{"appid": "portal"}]}},
        "get search suggestions",
    ),
    Endpoint(
        "store_search",
        lambda steam: steam.store.store_search("portal"),
        STORE_PREFIX + STORE_SEARCH,
        SEARCH,
        {"total": 3, "items": {"name": "Portal 2"}},
        "search the store",
    ),
]

ALL_ENDPOINTS = pytest.mark.parametrize(
    "endpoint", [pytest.param(endpoint, id=endpoint.name) for endpoint in ENDPOINTS]
)


def input_json(request: RecordedRequest) -> dict[str, Any]:
    """The decoded ``input_json`` of a service-method request."""
    return json.loads(request.params["input_json"])


@pytest.fixture
async def anonymous_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client with no credential at all."""
    async with Steam(settings=settings) as client:
        yield client


# -- all three methods ---------------------------------------------------------


@ALL_ENDPOINTS
async def test_call_is_one_get_to_documented_path(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [("GET", endpoint.path)]


@ALL_ENDPOINTS
async def test_call_sends_no_credential(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    sent = fake_steam.last
    assert "key" not in sent.query
    assert "access_token" not in sent.query
    assert not sent.form
    assert "Cookie" not in sent.headers
    assert "Authorization" not in sent.headers
    assert API_KEY not in str(sent.query)
    assert ACCESS_TOKEN not in str(sent.query)


@ALL_ENDPOINTS
async def test_call_works_without_any_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(anonymous_steam)

    assert len(fake_steam.requests) == 1


@ALL_ENDPOINTS
async def test_http_500_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(steam)

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == 500
    assert "HTTP 500" in str(excinfo.value)


@ALL_ENDPOINTS
async def test_malformed_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json=endpoint.malformed)

    with pytest.raises(ResponseParsingError, match=f"Failed to {endpoint.operation}"):
        await endpoint.call(steam)


@ALL_ENDPOINTS
async def test_html_body_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(
        fake_steam, text="<html>Service Unavailable</html>", content_type="text/html"
    )

    with pytest.raises(SteamAPIError, match="Invalid JSON response"):
        await endpoint.call(steam)


# -- get_items -----------------------------------------------------------------


async def test_get_items_sends_ids_context_and_basic_info_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    await steam.store.get_items([620, 440])

    assert list(fake_steam.last.params) == ["input_json"]
    assert input_json(fake_steam.last) == {
        "ids": [{"appid": 620}, {"appid": 440}],
        "context": US_ENGLISH,
        "data_request": {"include_basic_info": True},
    }


async def test_get_items_sends_every_requested_part(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    await steam.store.get_items(
        [620],
        language="german",
        country_code="DE",
        include_assets=True,
        include_release=True,
        include_platforms=True,
        include_ratings=True,
        include_tag_count=5,
        include_reviews=True,
        include_all_purchase_options=True,
        include_screenshots=True,
        include_trailers=True,
        include_supported_languages=True,
        include_full_description=True,
        include_links=True,
    )

    sent = input_json(fake_steam.last)
    assert sent["context"] == {
        "language": "german",
        "country_code": "DE",
        "steam_realm": 1,
    }
    assert sent["data_request"] == {
        "include_basic_info": True,
        "include_assets": True,
        "include_release": True,
        "include_platforms": True,
        "include_ratings": True,
        "include_tag_count": 5,
        "include_reviews": True,
        "include_all_purchase_options": True,
        "include_screenshots": True,
        "include_trailers": True,
        "include_supported_languages": True,
        "include_full_description": True,
        "include_links": True,
    }


async def test_get_items_leaves_unrequested_parts_out(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    await steam.store.get_items(620, include_basic_info=False, include_tag_count=0)

    assert input_json(fake_steam.last)["data_request"] == {}


@pytest.mark.parametrize(
    "appids",
    [
        pytest.param(620, id="int"),
        pytest.param([620], id="list"),
        pytest.param((620,), id="tuple"),
        pytest.param(range(620, 621), id="range"),
        pytest.param((appid for appid in [620]), id="generator"),
    ],
)
async def test_get_items_accepts_one_app_id_or_any_iterable(
    steam: Steam, fake_steam: FakeSteam, appids: Any
) -> None:
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    await steam.store.get_items(appids)

    assert input_json(fake_steam.last)["ids"] == [{"appid": 620}]


@pytest.mark.parametrize(
    "appids",
    [0, -1, 2**32, True, "620", b"620", 620.0, None, [620, 0], [620, "440"]],
    ids=repr,
)
async def test_get_items_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appids: Any
) -> None:
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    with pytest.raises(InvalidAppIDError):
        await steam.store.get_items(appids)

    assert fake_steam.requests == []


async def test_get_items_rejects_no_app_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    with pytest.raises(ValueError, match="At least one App ID"):
        await steam.store.get_items([])

    assert fake_steam.requests == []


async def test_get_items_parses_items(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    result = await steam.store.get_items([620, 440])

    portal2, tf2 = result.store_items
    assert (portal2.item_type, portal2.id, portal2.appid) == (
        EStoreItemType.APP,
        620,
        620,
    )
    assert (portal2.success, portal2.visible, portal2.name) == (1, True, "Portal 2")
    assert portal2.store_url_path == "app/620/Portal_2/"
    assert portal2.type == EStoreAppType.GAME
    assert portal2.is_free is False
    assert portal2.tagids[:3] == [1664, 1685, 3839]
    assert portal2.categories.controller_categoryids == [28]
    assert portal2.basic_info.short_description.startswith("The &quot;Perpetual")
    assert [p.name for p in portal2.basic_info.publishers] == ["Valve"]
    assert portal2.basic_info.developers[0].creator_clan_account_id == 4
    assert portal2.basic_info.franchises[0].name == "Portal"
    assert portal2.basic_info.franchises[0].creator_clan_account_id == 0
    assert [(t.tagid, t.weight) for t in portal2.tags][:2] == [
        (1664, 4810),
        (1685, 3236),
    ]
    assert portal2.assets.asset_url_format == "steam/apps/620/${FILENAME}?t=1745363004"
    assert portal2.assets.header == "header.jpg"
    assert portal2.release.steam_release_date == 1303171200
    assert portal2.release.is_coming_soon is False
    assert (portal2.platforms.windows, portal2.platforms.mac) == (True, True)
    assert portal2.platforms.steamos_linux is True
    assert portal2.platforms.vr_support.vrhmd is False
    assert (
        portal2.platforms.steam_deck_compat_category
        == ESteamDeckCompatibilityCategory.VERIFIED
    )
    assert (portal2.game_rating.type, portal2.game_rating.rating) == ("esrb", "e10")
    assert portal2.game_rating.descriptors == ["Fantasy Violence", "Mild Language"]
    summary = portal2.reviews.summary_filtered
    assert (summary.review_count, summary.percent_positive) == (443211, 98)
    assert summary.review_score == EUserReviewScore.OVERWHELMINGLY_POSITIVE
    assert summary.review_score_label == "Overwhelmingly Positive"
    assert portal2.reviews.summary_language_specific.review_count == 0
    assert tf2.is_free is True
    assert tf2.platforms.mac is False
    assert tf2.game_rating.required_age == 17


async def test_get_items_parses_purchase_options_and_64_bit_prices(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # int64 prices arrive as JSON strings ("199").
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    portal2 = (await steam.store.get_items(620)).store_items[0]

    best = portal2.best_purchase_option
    assert (best.packageid, best.purchase_option_name) == (7877, "Buy Portal 2")
    assert (best.final_price_in_cents, best.original_price_in_cents) == (199, 999)
    assert (best.formatted_final_price, best.discount_pct) == ("$1.99", 80)
    assert best.lowest_recent_price_in_cents == 199
    (discount,) = best.active_discounts
    assert (discount.discount_amount, discount.discount_end_date) == (800, 1760029200)
    assert best.package_group == "default"
    assert best.recurrence_info == {}
    package, bundle = portal2.purchase_options
    assert (package.packageid, package.bundleid) == (7877, 0)
    assert (bundle.packageid, bundle.bundleid) == (0, 234)
    assert (bundle.bundle_discount_pct, bundle.included_game_count) == (10, 2)
    assert bundle.price_before_bundle_discount == 398


async def test_get_items_free_app_has_default_purchase_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GET_ITEMS, json=ITEMS)

    tf2 = (await steam.store.get_items(440)).store_items[1]

    assert tf2.best_purchase_option.packageid == 0
    assert tf2.best_purchase_option.final_price_in_cents == 0
    assert tf2.best_purchase_option.included_game_count == 1
    assert tf2.purchase_options == []


@pytest.mark.parametrize("body", [EMPTY, {}], ids=["empty-response", "empty-body"])
async def test_get_items_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.api("GET", GET_ITEMS, json=body)

    result = await steam.store.get_items(620)

    assert result == StoreItems()
    assert result.store_items == []


async def test_get_items_parses_item_with_defaults_omitted(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Steam leaves out unset fields; the proto's default item_type is Invalid.
    fake_steam.api(
        "GET", GET_ITEMS, json={"response": {"store_items": [{"id": 9999999}]}}
    )

    (item,) = (await steam.store.get_items(9999999)).store_items

    assert item == StoreItem(id=9999999)
    assert item.item_type == EStoreItemType.INVALID
    assert item.type == EStoreAppType.GAME
    assert (item.success, item.visible, item.name) == (0, False, "")
    assert item.basic_info.publishers == []
    assert item.platforms.windows is False
    assert item.gid == ""
    assert item.trailers == {}


async def test_get_items_keeps_steam_spelling_of_country_restriction(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = {
        "response": {
            "store_items": [
                {"id": 620, "success": 1, "unvailable_for_country_restriction": True}
            ]
        }
    }
    fake_steam.api("GET", GET_ITEMS, json=body)

    (item,) = (await steam.store.get_items(620)).store_items

    assert item.unvailable_for_country_restriction is True


async def test_get_items_parses_requested_extras(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    item = {
        "item_type": 0,
        "id": 620,
        "success": 1,
        "screenshots": {
            "all_ages_screenshots": [
                {"filename": "ss_f3f6787d74739d3b2ec8a484b5c994b3d31ef325.jpg"},
                {
                    "filename": "ss_6a4f5afdaa98402de9cf0b59fed27bab3256a6f4.jpg",
                    "ordinal": 1,
                },
            ]
        },
        "supported_languages": [
            {"elanguage": 0, "supported": True, "full_audio": True, "subtitles": True},
            {"elanguage": 1, "supported": True, "subtitles": True},
        ],
        "links": [{"link_type": 1, "url": "https://www.youtube.com/valve"}],
        "full_description": "Portal 2 draws from the award-winning formula",
        "trailers": {"highlights": [{"trailer_name": "Portal 2 Trailer"}]},
        "gid": "5142807405693516043",
    }
    fake_steam.api("GET", GET_ITEMS, json={"response": {"store_items": [item]}})

    (parsed,) = (await steam.store.get_items(620)).store_items

    shots = parsed.screenshots.all_ages_screenshots
    assert [(s.filename[:11], s.ordinal) for s in shots] == [
        ("ss_f3f6787d", 0),
        ("ss_6a4f5afd", 1),
    ]
    english, german = parsed.supported_languages
    assert (english.elanguage, english.full_audio) == (0, True)
    assert (german.elanguage, german.full_audio, german.eadditionallanguage) == (
        1,
        False,
        -1,
    )
    assert [(link.link_type, link.text) for link in parsed.links] == [(1, "")]
    assert parsed.full_description.startswith("Portal 2 draws")
    assert parsed.trailers["highlights"][0]["trailer_name"] == "Portal 2 Trailer"
    assert parsed.gid == "5142807405693516043"


@pytest.mark.parametrize("key", ["full_description", "full_description_bbcode"])
async def test_get_items_reads_full_description_under_either_proto_name(
    steam: Steam, fake_steam: FakeSteam, key: str
) -> None:
    # Field 58 is named differently in the webui and steamclient protos.
    body = {"response": {"store_items": [{"id": 620, key: "[h1]Portal 2[/h1]"}]}}
    fake_steam.api("GET", GET_ITEMS, json=body)

    (item,) = (
        await steam.store.get_items(620, include_full_description=True)
    ).store_items

    assert item.full_description == "[h1]Portal 2[/h1]"


# -- search_suggestions --------------------------------------------------------


async def test_search_suggestions_sends_term_context_and_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SEARCH_SUGGESTIONS, json=SUGGESTIONS)

    await steam.store.search_suggestions("portal")

    assert list(fake_steam.last.params) == ["input_json"]
    assert input_json(fake_steam.last) == {
        "context": US_ENGLISH,
        "search_term": "portal",
        "max_results": 10,
        "data_request": {"include_basic_info": True},
        "use_spellcheck": False,
        "search_tags": False,
        "search_creators": False,
    }


async def test_search_suggestions_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SEARCH_SUGGESTIONS, json=SUGGESTIONS)
    filters = {"released_only": True, "type_filters": {"include_games": True}}

    await steam.store.search_suggestions(
        "portl",
        max_results=3,
        language="french",
        country_code="FR",
        use_spellcheck=True,
        search_tags=True,
        search_creators=True,
        filters=filters,
        include_basic_info=False,
        include_assets=True,
        include_release=True,
        include_platforms=True,
        include_reviews=True,
        include_tag_count=3,
    )

    assert input_json(fake_steam.last) == {
        "context": {"language": "french", "country_code": "FR", "steam_realm": 1},
        "search_term": "portl",
        "max_results": 3,
        "data_request": {
            "include_assets": True,
            "include_release": True,
            "include_platforms": True,
            "include_reviews": True,
            "include_tag_count": 3,
        },
        "use_spellcheck": True,
        "search_tags": True,
        "search_creators": True,
        "filters": filters,
    }


async def test_search_suggestions_sends_term_verbatim(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SEARCH_SUGGESTIONS, json=SUGGESTIONS)

    await steam.store.search_suggestions('Half-Life 2: "Episode" & Co ü')

    assert input_json(fake_steam.last)["search_term"] == 'Half-Life 2: "Episode" & Co ü'


async def test_search_suggestions_parses_matches(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SEARCH_SUGGESTIONS, json=SUGGESTIONS)

    result = await steam.store.search_suggestions("portal")

    assert result.metadata.total_matching_records == 214
    assert (result.metadata.start, result.metadata.count) == (0, 3)
    assert [item_id.appid for item_id in result.ids] == [620, 400, 1255980]
    assert result.ids[0].packageid == 0
    assert result.ids[0].salepagegid == ""
    portal2, portal, reloaded = result.store_items
    assert (portal2.name, portal.name, reloaded.name) == (
        "Portal 2",
        "Portal",
        "Portal Reloaded",
    )
    assert portal.best_purchase_option.final_price_in_cents == 999
    assert reloaded.type == EStoreAppType.MOD
    assert reloaded.is_free is True
    assert reloaded.related_items.parent_appid == 620
    assert reloaded.related_items.related_f2p.appid == 0
    assert reloaded.basic_info.publishers[0].name == "Jannis Brinkmann"


async def test_search_suggestions_parses_spellcheck_and_tag_matches(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = {
        "response": {
            "metadata": {
                "count": 2,
                "per_result_metadata": [
                    {
                        "id": {"appid": 620},
                        "score": 13.5,
                        "spellcheck_generated_result": True,
                    }
                ],
                "spellcheck_suggestions": ["portal"],
            },
            "ids": [{"appid": 620}, {"tagid": 1664}],
        }
    }
    fake_steam.api("GET", SEARCH_SUGGESTIONS, json=body)

    result = await steam.store.search_suggestions(
        "portl", use_spellcheck=True, search_tags=True
    )

    assert result.metadata.spellcheck_suggestions == ["portal"]
    (per_result,) = result.metadata.per_result_metadata
    assert (per_result.id.appid, per_result.score) == (620, 13.5)
    assert per_result.spellcheck_generated_result is True
    assert [(i.appid, i.tagid) for i in result.ids] == [(620, 0), (0, 1664)]
    assert result.store_items == []


@pytest.mark.parametrize("body", [EMPTY, {}], ids=["empty-response", "empty-body"])
async def test_search_suggestions_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.api("GET", SEARCH_SUGGESTIONS, json=body)

    result = await steam.store.search_suggestions("zzzzzzzzzz")

    assert result == SearchSuggestions()
    assert result.metadata.total_matching_records == 0
    assert result.ids == []


# -- store_search --------------------------------------------------------------


async def test_store_search_sends_term_language_and_country(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", STORE_SEARCH, json=SEARCH)

    await steam.store.store_search("portal")

    assert fake_steam.last.params == {"term": "portal", "l": "english", "cc": "US"}


async def test_store_search_sends_given_language_and_country(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", STORE_SEARCH, json=SEARCH)

    await steam.store.store_search(
        "Half-Life 2 & Co", language="german", country_code="DE"
    )

    assert fake_steam.last.params == {
        "term": "Half-Life 2 & Co",
        "l": "german",
        "cc": "DE",
    }


async def test_store_search_parses_results(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.store("GET", STORE_SEARCH, json=SEARCH)

    result = await steam.store.store_search("portal")

    assert isinstance(result, StoreSearchResult)
    assert result.total == 3
    portal2, portal, reloaded = result.items
    assert (portal2.type, portal2.id, portal2.name) == ("app", 620, "Portal 2")
    assert portal2.price is not None
    assert (portal2.price.currency, portal2.price.initial, portal2.price.final) == (
        "USD",
        999,
        199,
    )
    assert portal2.tiny_image.endswith("/apps/620/capsule_231x87.jpg?t=1745363004")
    assert portal2.metascore == "95"
    assert (
        portal2.platforms.windows,
        portal2.platforms.mac,
        portal2.platforms.linux,
    ) == (True, True, True)
    assert portal2.streamingvideo is False
    assert portal2.controller_support == "full"
    assert portal.controller_support == ""
    # Free apps come without a price, and unrated ones with metascore "".
    assert reloaded.price is None
    assert reloaded.metascore == ""
    assert (reloaded.platforms.mac, reloaded.platforms.linux) == (False, False)


@pytest.mark.parametrize(
    "body", [{"total": 0, "items": []}, {}], ids=["no-results", "empty-body"]
)
async def test_store_search_parses_empty_result(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.store("GET", STORE_SEARCH, json=body)

    result = await steam.store.store_search("zzzzzzzzzz")

    assert result == StoreSearchResult()
    assert (result.total, result.items) == (0, [])


async def test_store_search_parses_item_with_fields_missing(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store(
        "GET",
        STORE_SEARCH,
        json={"total": 1, "items": [{"id": 620, "name": "Portal 2"}]},
    )

    (item,) = (await steam.store.store_search("portal 2")).items

    assert (item.id, item.name, item.type) == (620, "Portal 2", "")
    assert item.price is None
    assert item.platforms.windows is False
    assert (item.metascore, item.controller_support) == ("", "")


@pytest.mark.parametrize("body", [None, [], "portal"], ids=repr)
async def test_store_search_non_object_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, body: Any
) -> None:
    fake_steam.store(
        "GET", STORE_SEARCH, text=json.dumps(body), content_type="application/json"
    )

    with pytest.raises(ResponseParsingError, match="Failed to search the store"):
        await steam.store.store_search("portal")


# == Milestone 2: charts, DLC, categories, featured items, query, top sellers ==
#
# Every method here but get_dlc_for_apps needs no credential and must send
# none. get_dlc_for_apps is about the signed-in user: it sends the access token
# and never the API key. All are GET service methods; their inputs go in one
# ``input_json`` parameter, except GetStoreCategories, whose inputs are flat.
#
# Fixtures:
# - store_get_games_by_concurrent_players.json and
#   store_get_weekly_top_sellers.json: real replies (with include_basic_info)
#   published by cbbsjj0314/picking-my-time-sink, cut to the first three ranks
# - store_get_most_played_games.json: a reply trimmed to two ranks, as
#   published in gofurry/steam-go's tests (it looks live; unverified)
# - store_get_store_categories.json: real categories from a GetStoreCategories
#   reply, as published by Tormak9970/TabMaster
# - store_get_dlc_for_apps.json, store_get_dlc_for_apps_solr.json,
#   store_get_items_to_feature.json, store_query.json: built from the protos
#   (field names, int64 as strings, defaults left out); ids, dates and texts
#   are illustrative, while their StoreItem bodies are real ones taken from the
#   top sellers reply

CONCURRENT = "/ISteamChartsService/GetGamesByConcurrentPlayers/v1/"
MOST_PLAYED = "/ISteamChartsService/GetMostPlayedGames/v1/"
DLC_FOR_APPS = "/IStoreBrowseService/GetDLCForApps/v1/"
DLC_SOLR = "/IStoreBrowseService/GetDLCForAppsSolr/v1/"
CATEGORIES = "/IStoreBrowseService/GetStoreCategories/v1/"
FEATURE = "/IStoreMarketingService/GetItemsToFeature/v1/"
QUERY = "/IStoreQueryService/Query/v1/"
TOP_SELLERS = "/IStoreTopSellersService/GetWeeklyTopSellers/v1/"

CONCURRENT_REPLY: dict[str, Any] = load_fixture(
    "store_get_games_by_concurrent_players.json"
)
MOST_PLAYED_REPLY: dict[str, Any] = load_fixture("store_get_most_played_games.json")
DLC_REPLY: dict[str, Any] = load_fixture("store_get_dlc_for_apps.json")
DLC_SOLR_REPLY: dict[str, Any] = load_fixture("store_get_dlc_for_apps_solr.json")
CATEGORIES_REPLY: dict[str, Any] = load_fixture("store_get_store_categories.json")
FEATURE_REPLY: dict[str, Any] = load_fixture("store_get_items_to_feature.json")
QUERY_REPLY: dict[str, Any] = load_fixture("store_query.json")
TOP_SELLERS_REPLY: dict[str, Any] = load_fixture("store_get_weekly_top_sellers.json")

KOREAN = {"language": "koreana", "country_code": "KR", "steam_realm": 1}
EVERY_DATA_OPTION = {
    "include_basic_info": True,
    "include_assets": True,
    "include_release": True,
    "include_platforms": True,
    "include_reviews": True,
    "include_tag_count": 5,
}

INVALID_APP_IDS_M2 = [0, -1, 2**32, True, "620", b"620", 620.0, None, [620, 0]]


@dataclass(frozen=True)
class ServiceEndpoint(Endpoint):
    """An Endpoint plus what it returns for an empty response."""

    empty: Any


M2_ENDPOINTS = [
    ServiceEndpoint(
        "get_games_by_concurrent_players",
        lambda steam: steam.store.get_games_by_concurrent_players(),
        CONCURRENT,
        CONCURRENT_REPLY,
        {"response": {"ranks": [{"appid": "cs2"}]}},
        "get games by concurrent players",
        GamesByConcurrentPlayers(),
    ),
    ServiceEndpoint(
        "get_most_played_games",
        lambda steam: steam.store.get_most_played_games(),
        MOST_PLAYED,
        MOST_PLAYED_REPLY,
        {"response": {"ranks": {"rank": 1}}},
        "get most played games",
        MostPlayedGames(),
    ),
    ServiceEndpoint(
        "get_dlc_for_apps_solr",
        lambda steam: steam.store.get_dlc_for_apps_solr([1091500, 730]),
        DLC_SOLR,
        DLC_SOLR_REPLY,
        {"response": {"dlc_lists": [{"dlc_appids": "many"}]}},
        "get DLC lists",
        [],
    ),
    ServiceEndpoint(
        "get_store_categories",
        lambda steam: steam.store.get_store_categories(),
        CATEGORIES,
        CATEGORIES_REPLY,
        {"response": {"categories": [{"categoryid": "controller"}]}},
        "get store categories",
        [],
    ),
    ServiceEndpoint(
        "get_items_to_feature",
        lambda steam: steam.store.get_items_to_feature(include_dailydeals=True),
        FEATURE,
        FEATURE_REPLY,
        {"response": {"daily_deals": [{"item_id": 730}]}},
        "get items to feature",
        ItemsToFeature(),
    ),
    ServiceEndpoint(
        "query",
        lambda steam: steam.store.query(item_types="games"),
        QUERY,
        QUERY_REPLY,
        {"response": {"ids": [{"appid": "portal"}]}},
        "query the store",
        StoreQueryResult(),
    ),
    ServiceEndpoint(
        "get_weekly_top_sellers",
        lambda steam: steam.store.get_weekly_top_sellers(),
        TOP_SELLERS,
        TOP_SELLERS_REPLY,
        {"response": {"next_page_start": "next"}},
        "get weekly top sellers",
        WeeklyTopSellers(),
    ),
]
KEYLESS_M2_ENDPOINTS = list(M2_ENDPOINTS)
M2_ENDPOINTS.append(
    ServiceEndpoint(
        "get_dlc_for_apps",
        lambda steam: steam.store.get_dlc_for_apps(1091500),
        DLC_FOR_APPS,
        DLC_REPLY,
        {"response": {"dlc_data": [{"price": "free"}]}},
        "get DLC for apps",
        DLCForApps(),
    )
)


def m2_endpoints(endpoints: list[ServiceEndpoint]) -> Any:
    return pytest.mark.parametrize(
        "endpoint", [pytest.param(endpoint, id=endpoint.name) for endpoint in endpoints]
    )


# Methods whose store data is optional and comes only with a data request.
ITEM_DATA_METHODS = pytest.mark.parametrize(
    ("method", "path", "reply"),
    [
        pytest.param(
            "get_games_by_concurrent_players",
            CONCURRENT,
            CONCURRENT_REPLY,
            id="get_games_by_concurrent_players",
        ),
        pytest.param(
            "get_most_played_games",
            MOST_PLAYED,
            MOST_PLAYED_REPLY,
            id="get_most_played_games",
        ),
        pytest.param(
            "get_items_to_feature", FEATURE, FEATURE_REPLY, id="get_items_to_feature"
        ),
        pytest.param(
            "get_weekly_top_sellers",
            TOP_SELLERS,
            TOP_SELLERS_REPLY,
            id="get_weekly_top_sellers",
        ),
    ],
)


@pytest.fixture
async def key_only_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client that has a Web API key but no access token."""
    async with Steam(api_key=API_KEY, settings=settings) as client:
        yield client


@pytest.fixture
async def token_only_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client that has an access token but no Web API key."""
    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as client:
        yield client


# -- every Milestone 2 method -------------------------------------------------


@m2_endpoints(M2_ENDPOINTS)
async def test_m2_call_is_one_get_to_v1_path(
    steam: Steam, fake_steam: FakeSteam, endpoint: ServiceEndpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [("GET", endpoint.path)]
    assert endpoint.path.endswith("/v1/")


@m2_endpoints(M2_ENDPOINTS)
async def test_m2_http_500_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: ServiceEndpoint
) -> None:
    endpoint.serve(fake_steam, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(steam)

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    assert ACCESS_TOKEN not in str(excinfo.value)


@m2_endpoints(M2_ENDPOINTS)
async def test_m2_malformed_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: ServiceEndpoint
) -> None:
    endpoint.serve(fake_steam, json=endpoint.malformed)

    with pytest.raises(ResponseParsingError, match=f"Failed to {endpoint.operation}"):
        await endpoint.call(steam)


@m2_endpoints(M2_ENDPOINTS)
async def test_m2_non_object_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: ServiceEndpoint
) -> None:
    endpoint.serve(fake_steam, json=["not", "an", "object"])

    with pytest.raises(ResponseParsingError, match=f"Failed to {endpoint.operation}"):
        await endpoint.call(steam)


@m2_endpoints(M2_ENDPOINTS)
@pytest.mark.parametrize("body", [EMPTY, {}], ids=["empty-response", "empty-body"])
async def test_m2_empty_response_gives_defaults(
    steam: Steam,
    fake_steam: FakeSteam,
    endpoint: ServiceEndpoint,
    body: dict[str, Any],
) -> None:
    endpoint.serve(fake_steam, json=body)

    assert await endpoint.call(steam) == endpoint.empty


@m2_endpoints(KEYLESS_M2_ENDPOINTS)
async def test_m2_keyless_call_sends_no_credential(
    steam: Steam, fake_steam: FakeSteam, endpoint: ServiceEndpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    sent = fake_steam.last
    assert "key" not in sent.query
    assert "access_token" not in sent.query
    assert not sent.form
    assert "Cookie" not in sent.headers
    assert "Authorization" not in sent.headers
    assert API_KEY not in str(sent.query)
    assert ACCESS_TOKEN not in str(sent.query)


@m2_endpoints(KEYLESS_M2_ENDPOINTS)
async def test_m2_keyless_call_works_without_any_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: ServiceEndpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(anonymous_steam)

    assert len(fake_steam.requests) == 1


# -- methods with optional store data -----------------------------------------


@ITEM_DATA_METHODS
async def test_item_data_method_sends_only_context_by_default(
    steam: Steam, fake_steam: FakeSteam, method: str, path: str, reply: Any
) -> None:
    fake_steam.api("GET", path, json=reply)

    await getattr(steam.store, method)()

    assert list(fake_steam.last.params) == ["input_json"]
    assert input_json(fake_steam.last) == {"context": US_ENGLISH}


@ITEM_DATA_METHODS
async def test_item_data_method_sends_context_and_every_data_option(
    steam: Steam, fake_steam: FakeSteam, method: str, path: str, reply: Any
) -> None:
    fake_steam.api("GET", path, json=reply)

    await getattr(steam.store, method)(
        language="koreana", country_code="KR", **EVERY_DATA_OPTION
    )

    assert input_json(fake_steam.last) == {
        "context": KOREAN,
        "data_request": EVERY_DATA_OPTION,
    }


# -- get_games_by_concurrent_players -------------------------------------------


async def test_get_games_by_concurrent_players_parses_ranks_and_items(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", CONCURRENT, json=CONCURRENT_REPLY)

    result = await steam.store.get_games_by_concurrent_players(include_basic_info=True)

    assert isinstance(result, GamesByConcurrentPlayers)
    assert result.last_update == 1773083732
    cs2, dota2, spire = result.ranks
    assert (cs2.rank, cs2.appid) == (1, 730)
    assert (cs2.concurrent_in_game, cs2.peak_in_game) == (1384410, 1509177)
    assert (cs2.item.id, cs2.item.name, cs2.item.is_free) == (
        730,
        "Counter-Strike 2",
        True,
    )
    assert cs2.item.basic_info.publishers[0].name == "Valve"
    assert dota2.item.basic_info.franchises[0].name == "Dota"
    assert (spire.rank, spire.appid, spire.item.is_early_access) == (3, 2868840, True)
    # int64 prices arrive as strings.
    assert spire.item.best_purchase_option.final_price_in_cents == 2499
    assert spire.item.best_purchase_option.formatted_final_price == "$24.99"


async def test_get_games_by_concurrent_players_rank_without_item_data(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # A real rank as Steam sends it when no data request was made.
    body = {
        "response": {
            "last_update": 1769340243,
            "ranks": [
                {
                    "rank": 1,
                    "appid": 730,
                    "concurrent_in_game": 1319976,
                    "peak_in_game": 1634036,
                }
            ],
        }
    }
    fake_steam.api("GET", CONCURRENT, json=body)

    (rank,) = (await steam.store.get_games_by_concurrent_players()).ranks

    assert (rank.appid, rank.concurrent_in_game) == (730, 1319976)
    assert rank.item == StoreItem()


# -- get_most_played_games ------------------------------------------------------


async def test_get_most_played_games_parses_ranks(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", MOST_PLAYED, json=MOST_PLAYED_REPLY)

    result = await steam.store.get_most_played_games()

    assert isinstance(result, MostPlayedGames)
    assert result.rollup_date == 1778198400
    cs2, l4d2 = result.ranks
    assert (cs2.rank, cs2.appid, cs2.last_week_rank, cs2.peak_in_game) == (
        1,
        730,
        1,
        1321704,
    )
    assert (l4d2.rank, l4d2.appid, l4d2.last_week_rank) == (34, 550, 31)
    assert l4d2.daily_active_players == 0
    assert l4d2.item == StoreItem()


async def test_get_most_played_games_parses_requested_item_and_new_entry(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = {
        "response": {
            "rollup_date": 1778198400,
            "ranks": [
                {
                    "rank": 7,
                    "appid": 2868840,
                    "item": {"id": 2868840, "success": 1, "name": "Slay the Spire 2"},
                    "peak_in_game": 568884,
                    "daily_active_players": 1200345,
                }
            ],
        }
    }
    fake_steam.api("GET", MOST_PLAYED, json=body)

    (rank,) = (await steam.store.get_most_played_games(include_basic_info=True)).ranks

    assert rank.item.name == "Slay the Spire 2"
    assert rank.daily_active_players == 1200345
    # Steam leaves last_week_rank out for a game that was not ranked.
    assert rank.last_week_rank == 0


# -- get_dlc_for_apps -------------------------------------------------------------


async def test_get_dlc_for_apps_sends_access_token_not_api_key(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_FOR_APPS, json=DLC_REPLY)

    await steam.store.get_dlc_for_apps([1091500, 620])

    sent = fake_steam.last
    assert set(sent.params) == {"input_json", "access_token"}
    assert sent.params["access_token"] == ACCESS_TOKEN
    assert API_KEY not in str(sent.query)
    assert "Authorization" not in sent.headers
    assert input_json(sent) == {"appids": [{"appid": 1091500}, {"appid": 620}]}


async def test_get_dlc_for_apps_sends_country_context(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_FOR_APPS, json=DLC_REPLY)

    await steam.store.get_dlc_for_apps(1091500, country_code="DE")

    assert input_json(fake_steam.last) == {
        "appids": [{"appid": 1091500}],
        "context": {"country_code": "DE", "steam_realm": 1},
    }


async def test_get_dlc_for_apps_works_with_access_token_only(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_FOR_APPS, json=DLC_REPLY)

    await token_only_steam.store.get_dlc_for_apps(1091500)

    assert set(fake_steam.last.params) == {"input_json", "access_token"}


async def test_get_dlc_for_apps_with_api_key_only_raises_before_any_request(
    key_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_FOR_APPS, json=DLC_REPLY)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await key_only_steam.store.get_dlc_for_apps(1091500)

    assert fake_steam.requests == []


async def test_get_dlc_for_apps_without_credentials_raises_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_FOR_APPS, json=DLC_REPLY)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await anonymous_steam.store.get_dlc_for_apps(1091500)

    assert fake_steam.requests == []


@pytest.mark.parametrize("appids", INVALID_APP_IDS_M2, ids=repr)
async def test_get_dlc_for_apps_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appids: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.store.get_dlc_for_apps(appids)

    assert fake_steam.requests == []


async def test_get_dlc_for_apps_rejects_no_app_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(ValueError, match="At least one App ID"):
        await steam.store.get_dlc_for_apps([])

    assert fake_steam.requests == []


async def test_get_dlc_for_apps_parses_dlc_and_playtime(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_FOR_APPS, json=DLC_REPLY)

    result = await steam.store.get_dlc_for_apps(1091500)

    assert isinstance(result, DLCForApps)
    paid, free, upcoming = result.dlc_data
    assert isinstance(paid, StoreDLCData)
    # model_dump, not a StoreDLCData(...) literal: the model ignores unknown
    # keywords, so a misnamed field would compare equal to itself.
    assert paid.model_dump() == {
        "appid": 2138330,
        "parentappid": 1091500,
        "release_date": 1695686400,
        "coming_soon": False,
        "price": 2999,  # an int64, sent as the string "2999"
        "discount": 20,
        "free": False,
    }
    assert (free.appid, free.parentappid) == (2060310, 1091500)
    assert (free.free, free.price, free.coming_soon) == (True, 0, False)
    assert (upcoming.coming_soon, upcoming.release_date, upcoming.price) == (
        True,
        0,
        999,
    )
    (playtime,) = result.playtime
    assert (playtime.appid, playtime.playtime, playtime.last_played) == (
        1091500,
        5423,
        1727740800,
    )


# -- get_dlc_for_apps_solr ------------------------------------------------------


async def test_get_dlc_for_apps_solr_sends_context_and_app_ids(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_SOLR, json=DLC_SOLR_REPLY)

    await steam.store.get_dlc_for_apps_solr([1091500, 730])

    assert list(fake_steam.last.params) == ["input_json"]
    assert input_json(fake_steam.last) == {
        "context": US_ENGLISH,
        "appids": [1091500, 730],
    }


async def test_get_dlc_for_apps_solr_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_SOLR, json=DLC_SOLR_REPLY)

    await steam.store.get_dlc_for_apps_solr(
        1091500, flavor="popular", count=5, language="koreana", country_code="KR"
    )

    assert input_json(fake_steam.last) == {
        "context": KOREAN,
        "appids": [1091500],
        "flavor": "popular",
        "count": 5,
    }


@pytest.mark.parametrize("appids", INVALID_APP_IDS_M2, ids=repr)
async def test_get_dlc_for_apps_solr_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appids: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.store.get_dlc_for_apps_solr(appids)

    assert fake_steam.requests == []


async def test_get_dlc_for_apps_solr_rejects_no_app_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(ValueError, match="At least one App ID"):
        await steam.store.get_dlc_for_apps_solr(())

    assert fake_steam.requests == []


async def test_get_dlc_for_apps_solr_parses_lists(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", DLC_SOLR, json=DLC_SOLR_REPLY)

    cyberpunk, cs2 = await steam.store.get_dlc_for_apps_solr([1091500, 730])

    assert isinstance(cyberpunk, AppDLCList)
    assert cyberpunk.model_dump() == {
        "parent_appid": 1091500,
        "dlc_appids": [2138330, 2060310],
    }
    # An app without DLC comes back with its id only.
    assert (cs2.parent_appid, cs2.dlc_appids) == (730, [])


# -- get_store_categories ---------------------------------------------------------


async def test_get_store_categories_sends_flat_language(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", CATEGORIES, json=CATEGORIES_REPLY)

    await steam.store.get_store_categories()

    assert fake_steam.last.params == {"language": "english"}


async def test_get_store_categories_sends_elanguage(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", CATEGORIES, json=CATEGORIES_REPLY)

    await steam.store.get_store_categories(language="german", elanguage=0)

    assert fake_steam.last.params == {"language": "german", "elanguage": "0"}


async def test_get_store_categories_parses_categories(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", CATEGORIES, json=CATEGORIES_REPLY)

    controller, single, mmo, cards, vac = await steam.store.get_store_categories()

    assert isinstance(controller, StoreCategory)
    assert controller.model_dump() == {
        "categoryid": 28,
        "type": EStoreCategoryType.CONTROLLER_SUPPORT,
        "internal_name": "Full Controller Support",
        "display_name": "Full controller support",
        "image_url": "public/images/v6/ico/ico_controller.png",
        "show_in_search": True,
        "computed": False,
        "edit_url": "",
        "edit_sort_order": 0,
    }
    assert (single.categoryid, single.type) == (2, EStoreCategoryType.SUPPORTED_PLAYERS)
    # Steam leaves show_in_search out when it is false.
    assert (mmo.categoryid, mmo.show_in_search) == (20, False)
    assert (cards.type, vac.type) == (EStoreCategoryType.FEATURE,) * 2
    assert vac.display_name == "Valve Anti-Cheat enabled"
    assert (vac.computed, vac.edit_url, vac.edit_sort_order) == (False, "", 0)


async def test_get_store_categories_category_type_left_out_is_category(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Type 0 (k_EStoreCategoryType_Category) is the default, so Steam omits it.
    body = {"response": {"categories": [{"categoryid": 999, "display_name": "X"}]}}
    fake_steam.api("GET", CATEGORIES, json=body)

    (category,) = await steam.store.get_store_categories()

    assert category.type == EStoreCategoryType.CATEGORY


# -- get_items_to_feature ---------------------------------------------------------


async def test_get_items_to_feature_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FEATURE, json=FEATURE_REPLY)

    await steam.store.get_items_to_feature(
        language="koreana",
        country_code="KR",
        spotlight_location="frontpage",
        spotlight_category="main",
        spotlight_genre_id=3,
        include_dailydeals=True,
        include_top_specials_count=10,
        include_purchase_recommendations=True,
        include_basic_info=True,
    )

    assert input_json(fake_steam.last) == {
        "context": KOREAN,
        "data_request": {"include_basic_info": True},
        "include_top_specials_count": 10,
        "include_spotlights": {
            "location": "frontpage",
            "category": "main",
            "genre_id": 3,
        },
        "include_dailydeals": True,
        "include_purchase_recommendations": True,
    }


async def test_get_items_to_feature_include_spotlights_sends_empty_filter(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FEATURE, json=FEATURE_REPLY)

    await steam.store.get_items_to_feature(include_spotlights=True)

    assert input_json(fake_steam.last) == {
        "context": US_ENGLISH,
        "include_spotlights": {},
    }


async def test_get_items_to_feature_parses_spotlights_and_capsules(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FEATURE, json=FEATURE_REPLY)

    result = await steam.store.get_items_to_feature(
        include_spotlights=True,
        include_dailydeals=True,
        include_top_specials_count=2,
        include_basic_info=True,
    )

    assert isinstance(result, ItemsToFeature)
    (spotlight,) = result.spotlights
    assert spotlight.item_id == StoreItemID(appid=3764200)
    assert spotlight.associated_item.name == "Resident Evil Requiem"
    assert spotlight.spotlight_title == "Resident Evil Requiem"
    assert spotlight.spotlight_template == "default"
    assert spotlight.spotlight_body == "Requiem for the dead. Nightmare for the living."
    assert spotlight.asset_url == (
        "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/3764200/"
        "spotlight.jpg"
    )
    assert spotlight.spotlight_link_url == "https://store.steampowered.com/app/3764200/"
    assert (spotlight.start_date, spotlight.end_date) == (1771891200, 1772496000)
    (deal,) = result.daily_deals
    assert (deal.item_id.appid, deal.item.name) == (730, "Counter-Strike 2")
    apex, package = result.specials
    assert apex.item.basic_info.developers[0].name == "Respawn"
    # A capsule Steam sent without item data.
    assert package.item_id == StoreItemID(packageid=1324561)
    assert package.item == StoreItem()
    assert result.purchase_recommendations == []


# -- query --------------------------------------------------------------------------


async def test_query_sends_page_context_and_basic_info_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY, json=QUERY_REPLY)

    await steam.store.query()

    assert list(fake_steam.last.params) == ["input_json"]
    assert input_json(fake_steam.last) == {
        "query": {"start": 0, "count": 10},
        "context": US_ENGLISH,
        "data_request": {"include_basic_info": True},
    }


async def test_query_sends_every_option(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", QUERY, json=QUERY_REPLY)

    await steam.store.query(
        start=20,
        count=2,
        sort=12,
        released_only=True,
        coming_soon_only=True,
        item_types=["games", "dlc"],
        dlc_for_appid=1091500,
        tagids_must_match=[19, 1663],
        tagids_exclude=9130,
        only_free_items=True,
        exclude_free_items=True,
        min_discount_percent=50,
        content_descriptors_must_match=[2],
        content_descriptors_excluded=(3, 4),
        query_name="steamy-py",
        language="koreana",
        country_code="KR",
        override_country_code="US",
        include_basic_info=False,
        include_assets=True,
        include_tag_count=3,
    )

    assert input_json(fake_steam.last) == {
        "query_name": "steamy-py",
        "query": {
            "start": 20,
            "count": 2,
            "sort": 12,
            "filters": {
                "released_only": True,
                "coming_soon_only": True,
                "type_filters": {
                    "include_games": True,
                    "include_dlc": True,
                    "dlc_for_appid": 1091500,
                },
                "tagids_must_match": [{"tagids": [19]}, {"tagids": [1663]}],
                "tagids_exclude": [9130],
                "price_filters": {
                    "only_free_items": True,
                    "exclude_free_items": True,
                    "min_discount_percent": 50,
                },
                "content_descriptors_must_match": [2],
                "content_descriptors_excluded": [3, 4],
            },
        },
        "context": KOREAN,
        "data_request": {"include_assets": True, "include_tag_count": 3},
        "override_country_code": "US",
    }


async def test_query_merges_raw_filters_over_keyword_filters(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY, json=QUERY_REPLY)

    await steam.store.query(
        released_only=True,
        item_types="games",
        filters={"released_only": False, "parent_appids": [620]},
    )

    assert input_json(fake_steam.last)["query"]["filters"] == {
        "released_only": False,
        "type_filters": {"include_games": True},
        "parent_appids": [620],
    }


async def test_query_without_data_options_sends_no_data_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", QUERY, json=QUERY_REPLY)

    await steam.store.query(include_basic_info=False, tagids_exclude=[])

    assert input_json(fake_steam.last) == {
        "query": {"start": 0, "count": 10},
        "context": US_ENGLISH,
    }


@pytest.mark.parametrize(
    "item_types", ["game", ["games", "tools"], [None], b"games"], ids=repr
)
async def test_query_rejects_unknown_item_type_before_any_request(
    steam: Steam, fake_steam: FakeSteam, item_types: Any
) -> None:
    with pytest.raises(ValueError, match="Unknown item type"):
        await steam.store.query(item_types=item_types)

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    "option",
    [
        "tagids_must_match",
        "tagids_exclude",
        "content_descriptors_must_match",
        "content_descriptors_excluded",
    ],
)
@pytest.mark.parametrize(
    "value", [True, 0, -1, 2**31, "19", b"19", 1.5, [19, None], [19, False]], ids=repr
)
async def test_query_rejects_invalid_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam, option: str, value: Any
) -> None:
    with pytest.raises(ValueError, match="Invalid"):
        await steam.store.query(**{option: value})

    assert fake_steam.requests == []


@pytest.mark.parametrize("appid", [0, -1, True, 2**32, "620"], ids=repr)
async def test_query_rejects_invalid_dlc_for_appid_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appid: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.store.query(dlc_for_appid=appid)

    assert fake_steam.requests == []


async def test_query_parses_matches(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", QUERY, json=QUERY_REPLY)

    result = await steam.store.query(count=2, item_types="games")

    assert isinstance(result, StoreQueryResult)
    assert result.metadata.total_matching_records == 1873
    assert (result.metadata.start, result.metadata.count) == (0, 2)
    assert result.ids == [StoreItemID(appid=730), StoreItemID(appid=1172470)]
    cs2, apex = result.store_items
    assert (cs2.name, cs2.is_free) == ("Counter-Strike 2", True)
    assert apex.categories.controller_categoryids == [28]
    assert apex.basic_info.franchises[0].name == "Apex Legends"


# -- get_weekly_top_sellers -------------------------------------------------------


async def test_get_weekly_top_sellers_sends_chart_country_week_and_page(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TOP_SELLERS, json=TOP_SELLERS_REPLY)

    await steam.store.get_weekly_top_sellers(
        chart_country_code="KR",
        language="koreana",
        country_code="KR",
        start_date=1771891200,
        page_start=10,
        page_count=10,
    )

    assert input_json(fake_steam.last) == {
        "country_code": "KR",
        "context": KOREAN,
        "start_date": 1771891200,
        "page_start": 10,
        "page_count": 10,
    }


async def test_get_weekly_top_sellers_parses_ranks(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TOP_SELLERS, json=TOP_SELLERS_REPLY)

    result = await steam.store.get_weekly_top_sellers(include_basic_info=True)

    assert isinstance(result, WeeklyTopSellers)
    assert (result.start_date, result.next_page_start) == (1771891200, 10)
    requiem, cs2, apex = result.ranks
    assert (
        requiem.rank,
        requiem.appid,
        requiem.last_week_rank,
        requiem.consecutive_weeks,
        requiem.first_top100,
    ) == (1, 3764200, 2, 8, False)
    best = requiem.item.best_purchase_option
    assert (best.packageid, best.final_price_in_cents) == (1324561, 6999)
    assert best.formatted_final_price == "$69.99"
    assert requiem.item.basic_info.franchises[0].name == "Resident Evil"
    assert (cs2.rank, cs2.consecutive_weeks, cs2.item.is_free) == (2, 708, True)
    assert (apex.rank, apex.appid, apex.last_week_rank) == (3, 1172470, 5)
    assert apex.item.name == "Apex Legends™"


async def test_get_weekly_top_sellers_parses_new_entry_without_item(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = {
        "response": {
            "start_date": 1771891200,
            "ranks": [
                {
                    "rank": 9,
                    "appid": 3065800,
                    "consecutive_weeks": 1,
                    "first_top100": True,
                }
            ],
        }
    }
    fake_steam.api("GET", TOP_SELLERS, json=body)

    result = await steam.store.get_weekly_top_sellers()

    (rank,) = result.ranks
    assert (rank.last_week_rank, rank.first_top100) == (0, True)
    assert rank.item == StoreItem()
    assert result.next_page_start == 0


async def test_get_weekly_top_sellers_country_code_goes_only_in_context(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # store_get_weekly_top_sellers_kr.json: a real reply to a request with a
    # "KR" context and no top-level country_code (cbbsjj0314/picking-my-time-
    # sink topsellers_kr.payload.json, cut to the first three ranks). Its ranks
    # are the Korean chart, not the global one, and its prices are in won.
    fake_steam.api(
        "GET", TOP_SELLERS, json=load_fixture("store_get_weekly_top_sellers_kr.json")
    )

    result = await steam.store.get_weekly_top_sellers(
        country_code="KR", include_basic_info=True
    )

    assert input_json(fake_steam.last) == {
        "context": {"language": "english", "country_code": "KR", "steam_realm": 1},
        "data_request": {"include_basic_info": True},
    }
    assert (result.start_date, result.next_page_start) == (1771891200, 10)
    pubg, requiem, limbus = result.ranks
    assert (pubg.rank, pubg.appid, pubg.item.name, pubg.item.is_free) == (
        1,
        578080,
        "PUBG: BATTLEGROUNDS",
        True,
    )
    assert (requiem.last_week_rank, requiem.consecutive_weeks) == (12, 8)
    best = requiem.item.best_purchase_option
    assert (best.final_price_in_cents, best.formatted_final_price) == (
        7980000,
        "₩ 79,800",
    )
    assert (limbus.rank, limbus.appid) == (3, 1973530)


# == Milestone 2, part 2: community apps, follows, tags, interest state,
# == package details and app reviews
#
# Credentials:
# - get_community_apps, get_games_followed, get_tag_list, get_package_details,
#   get_app_reviews and iter_app_reviews send none. GetTagList is called
#   keyless by published clients (embiem/go-web-template, safwyls/winnow:
#   "verified live ... keyless"), GetApps by several (Ntolgka/SteamDeals,
#   ClypLabs/ClypDat, macieklamberski/feedscout ...), GetGamesFollowed by
#   Grinv/steam-games-mcp ("Keyless", needs a public profile).
# - get_user_game_interest_state is about the signed-in user: it POSTs (the
#   verb in xPaw's API data) with the access token only, in the form body.
#
# Fixtures:
# - store_get_tag_list.json: a real reply, as published by
#   embiem/go-web-template (steam/testdata/gettaglist_english.json; the same
#   bytes are in safwyls/winnow), cut to the first six tags
# - store_get_package_details.json: a real reply, as published by
#   patcky/pdx-tech-challenge (example-response.json)
# - store_get_app_reviews.json: a real reply for app 2238240, as published by
#   rohand995/GoodGames (steam_data_samples/app_2238240_reviews.json), cut to
#   three reviews; it has string and number weighted_vote_score values and a
#   developer response
# - store_get_app_reviews_deck.json: a real reply for RimWorld, as published by
#   Saturn91/steamRevenueCalculation (example.json), cut to two reviews; its
#   cursor holds "+" and "="
# - store_get_community_apps.json, store_get_games_followed.json,
#   store_get_user_game_interest_state.json: built from the protos
#   (CCDDBAppDetailCommon, CStore_GetGamesFollowed_Response,
#   CStore_GetUserGameInterestState_Response; defaults left out). Names and
#   icon hashes are real (the Portal 2 icon as recorded by feedscout's tests,
#   the TF2 one from game_owned_games.json); flags, descriptor ids and queue
#   states are illustrative.

COMMUNITY_APPS = "/ICommunityService/GetApps/v1/"
GAMES_FOLLOWED = "/IStoreService/GetGamesFollowed/v1/"
TAG_LIST = "/IStoreService/GetTagList/v1/"
INTEREST_STATE = "/IStoreService/GetUserGameInterestState/v1/"
PACKAGE_DETAILS = "/packagedetails/"
REVIEWS_APPID = 2238240
APP_REVIEWS = f"/appreviews/{REVIEWS_APPID}"

COMMUNITY_APPS_REPLY: dict[str, Any] = load_fixture("store_get_community_apps.json")
GAMES_FOLLOWED_REPLY: dict[str, Any] = load_fixture("store_get_games_followed.json")
TAG_LIST_REPLY: dict[str, Any] = load_fixture("store_get_tag_list.json")
INTEREST_REPLY: dict[str, Any] = load_fixture("store_get_user_game_interest_state.json")
PACKAGE_REPLY: dict[str, Any] = load_fixture("store_get_package_details.json")
REVIEWS_REPLY: dict[str, Any] = load_fixture("store_get_app_reviews.json")
DECK_REVIEWS_REPLY: dict[str, Any] = load_fixture("store_get_app_reviews_deck.json")

DEFAULT_REVIEW_PARAMS = {
    "json": "1",
    "filter": "all",
    "language": "all",
    "cursor": "*",
    "review_type": "all",
    "purchase_type": "all",
    "num_per_page": "20",
}

INVALID_STEAM_IDS = [
    0,
    True,
    "",
    "abc",
    b"76561197960435530",
    None,
    76561197960265728,  # account id 0
    "76561197960435530 ",
]
INVALID_PACKAGE_IDS = [0, -1, 2**32, True, "42467", b"42467", 1.5, None, [42467, 0]]


@dataclass(frozen=True)
class Part2Call:
    """One part 2 method, called with realistic arguments."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    verb: str
    path: str  # as the fake server sees it
    reply: Any
    malformed: Any  # JSON that does not fit the method's model
    operation: str  # what the error message says failed

    def serve(self, fake_steam: FakeSteam, **reply: Any) -> None:
        """Register ``reply`` (default: the realistic one) for this method."""
        reply = reply or {"json": self.reply}
        fake_steam.add(self.verb, self.path, **reply)


PART2_CALLS = [
    Part2Call(
        "get_community_apps",
        lambda steam: steam.store.get_community_apps([620, 440]),
        "GET",
        COMMUNITY_APPS,
        COMMUNITY_APPS_REPLY,
        {"response": {"apps": [{"appid": "portal"}]}},
        "get community apps",
    ),
    Part2Call(
        "get_games_followed",
        lambda steam: steam.store.get_games_followed(STEAMID),
        "GET",
        GAMES_FOLLOWED,
        GAMES_FOLLOWED_REPLY,
        {"response": {"appids": ["portal"]}},
        "get followed games",
    ),
    Part2Call(
        "get_tag_list",
        lambda steam: steam.store.get_tag_list(),
        "GET",
        TAG_LIST,
        TAG_LIST_REPLY,
        {"response": {"tags": [{"tagid": "strategy"}]}},
        "get tag list",
    ),
    Part2Call(
        "get_package_details",
        lambda steam: steam.store.get_package_details(42467),
        "GET",
        STORE_PREFIX + PACKAGE_DETAILS,
        PACKAGE_REPLY,
        {"42467": {"success": True, "data": {"apps": "many"}}},
        "get package details",
    ),
    Part2Call(
        "get_app_reviews",
        lambda steam: steam.store.get_app_reviews(REVIEWS_APPID),
        "GET",
        STORE_PREFIX + APP_REVIEWS,
        REVIEWS_REPLY,
        {"success": 1, "reviews": [{"votes_up": "many"}]},
        "get app reviews",
    ),
]
KEYLESS_PART2_CALLS = list(PART2_CALLS)
INTEREST_CALL = Part2Call(
    "get_user_game_interest_state",
    lambda steam: steam.store.get_user_game_interest_state(620),
    "POST",
    INTEREST_STATE,
    INTEREST_REPLY,
    {"response": {"in_queues": "all"}},
    "get user game interest state",
)
PART2_CALLS.append(INTEREST_CALL)

# The service methods and what they return for an empty response.
PART2_EMPTY = [
    pytest.param(PART2_CALLS[0], [], id="get_community_apps"),
    pytest.param(PART2_CALLS[1], [], id="get_games_followed"),
    pytest.param(PART2_CALLS[2], TagList(), id="get_tag_list"),
    pytest.param(INTEREST_CALL, UserGameInterestState(), id=INTEREST_CALL.name),
]


def part2_calls(calls: list[Part2Call]) -> Any:
    return pytest.mark.parametrize(
        "call", [pytest.param(call, id=call.name) for call in calls]
    )


def sent(pairs: Any) -> dict[str, str]:
    """``pairs`` (a query string or form body) as a dict, checking that no
    name was sent twice."""
    items = list(pairs.items())
    assert len({name for name, _ in items}) == len(items), items
    return dict(items)


def assert_no_credential(request: RecordedRequest) -> None:
    assert "key" not in request.query
    assert "access_token" not in request.query
    assert not request.form
    assert "Cookie" not in request.headers
    assert "Authorization" not in request.headers
    assert API_KEY not in str(request.query)
    assert ACCESS_TOKEN not in str(request.query)


# -- every part 2 method ------------------------------------------------------------


@part2_calls(PART2_CALLS)
async def test_part2_call_is_one_request_with_documented_verb_and_path(
    steam: Steam, fake_steam: FakeSteam, call: Part2Call
) -> None:
    call.serve(fake_steam)

    await call.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [(call.verb, call.path)]


@part2_calls(PART2_CALLS)
async def test_part2_http_500_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, call: Part2Call
) -> None:
    call.serve(fake_steam, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await call.call(steam)

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    assert ACCESS_TOKEN not in str(excinfo.value)


@part2_calls(PART2_CALLS)
async def test_part2_malformed_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, call: Part2Call
) -> None:
    call.serve(fake_steam, json=call.malformed)

    with pytest.raises(ResponseParsingError, match=f"Failed to {call.operation}"):
        await call.call(steam)


@part2_calls(PART2_CALLS)
async def test_part2_html_body_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, call: Part2Call
) -> None:
    call.serve(
        fake_steam, text="<html>Service Unavailable</html>", content_type="text/html"
    )

    with pytest.raises(SteamAPIError, match="Invalid JSON response"):
        await call.call(steam)


@part2_calls([c for c in PART2_CALLS if c.name != "get_package_details"])
async def test_part2_non_object_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, call: Part2Call
) -> None:
    call.serve(fake_steam, json=["not", "an", "object"])

    with pytest.raises(ResponseParsingError, match=f"Failed to {call.operation}"):
        await call.call(steam)


@pytest.mark.parametrize(("call", "empty"), PART2_EMPTY)
@pytest.mark.parametrize("body", [EMPTY, {}], ids=["empty-response", "empty-body"])
async def test_part2_empty_response_gives_defaults(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Part2Call,
    empty: Any,
    body: dict[str, Any],
) -> None:
    call.serve(fake_steam, json=body)

    assert await call.call(steam) == empty


@part2_calls(KEYLESS_PART2_CALLS)
async def test_part2_keyless_call_sends_no_credential(
    steam: Steam, fake_steam: FakeSteam, call: Part2Call
) -> None:
    call.serve(fake_steam)

    await call.call(steam)

    assert_no_credential(fake_steam.last)


@part2_calls(KEYLESS_PART2_CALLS)
async def test_part2_keyless_call_works_without_any_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam, call: Part2Call
) -> None:
    call.serve(fake_steam)

    await call.call(anonymous_steam)

    assert len(fake_steam.requests) == 1


# -- get_community_apps -------------------------------------------------------------


async def test_get_community_apps_sends_indexed_app_ids_only(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", COMMUNITY_APPS, json=COMMUNITY_APPS_REPLY)

    await steam.store.get_community_apps([620, 440])

    assert sent(fake_steam.last.query) == {"appids[0]": "620", "appids[1]": "440"}


async def test_get_community_apps_sends_one_app_id_and_elanguage(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", COMMUNITY_APPS, json=COMMUNITY_APPS_REPLY)

    await steam.store.get_community_apps(620, language=6)

    assert sent(fake_steam.last.query) == {"appids[0]": "620", "language": "6"}


@pytest.mark.parametrize("appids", INVALID_APP_IDS_M2, ids=repr)
async def test_get_community_apps_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appids: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.store.get_community_apps(appids)

    assert fake_steam.requests == []


async def test_get_community_apps_rejects_no_app_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(ValueError, match="At least one App ID"):
        await steam.store.get_community_apps([])

    assert fake_steam.requests == []


async def test_get_community_apps_parses_apps(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", COMMUNITY_APPS, json=COMMUNITY_APPS_REPLY)

    portal2, tf2 = await steam.store.get_community_apps([620, 440])

    assert isinstance(portal2, CommunityApp)
    # model_dump, not a CommunityApp(...) literal: the model ignores unknown
    # keywords, so a misnamed field would compare equal to itself.
    assert portal2.model_dump() == {
        "appid": 620,
        "name": "Portal 2",
        "icon": "25a5a16b2423bf7487ac5340b5b0948cef48c5f8",
        "tool": False,
        "demo": False,
        "media": False,
        "community_visible_stats": True,
        "friendly_name": "",
        "propagation": "",
        "has_adult_content": False,
        "is_visible_in_steam_china": False,
        "app_type": 1,
        "has_adult_content_sex": False,
        "has_adult_content_violence": False,
        "content_descriptorids": [],
        "content_descriptorids_including_dlc": [],
    }
    assert (tf2.appid, tf2.name) == (440, "Team Fortress 2")
    assert tf2.content_descriptorids == [2, 5]
    assert tf2.content_descriptorids_including_dlc == [2, 5]


async def test_get_community_apps_parses_every_proto_field(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    app = {
        "appid": 1,
        "name": "Demo",
        "icon": "abc",
        "tool": True,
        "demo": True,
        "media": True,
        "community_visible_stats": True,
        "friendly_name": "demo",
        "propagation": "x",
        "has_adult_content": True,
        "is_visible_in_steam_china": True,
        "app_type": 8,
        "has_adult_content_sex": True,
        "has_adult_content_violence": True,
        "content_descriptorids": [3],
        "content_descriptorids_including_dlc": [3, 4],
    }
    fake_steam.api("GET", COMMUNITY_APPS, json={"response": {"apps": [app]}})

    (parsed,) = await steam.store.get_community_apps(1)

    assert parsed.model_dump() == app


# -- get_games_followed -------------------------------------------------------------


@pytest.mark.parametrize(
    "steamid",
    [STEAMID, int(STEAMID), SteamID(STEAMID)],
    ids=["str", "int", "SteamID"],
)
async def test_get_games_followed_sends_steamid_only(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    fake_steam.api("GET", GAMES_FOLLOWED, json=GAMES_FOLLOWED_REPLY)

    await steam.store.get_games_followed(steamid)

    assert sent(fake_steam.last.query) == {"steamid": STEAMID}


@pytest.mark.parametrize("steamid", INVALID_STEAM_IDS, ids=repr)
async def test_get_games_followed_rejects_invalid_steam_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    with pytest.raises(InvalidSteamIDError):
        await steam.store.get_games_followed(steamid)

    assert fake_steam.requests == []


async def test_get_games_followed_returns_app_ids(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GAMES_FOLLOWED, json=GAMES_FOLLOWED_REPLY)

    assert await steam.store.get_games_followed(STEAMID) == [620, 440, 1091500]


# -- get_tag_list -------------------------------------------------------------------


async def test_get_tag_list_sends_english_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TAG_LIST, json=TAG_LIST_REPLY)

    await steam.store.get_tag_list()

    assert sent(fake_steam.last.query) == {"language": "english"}


async def test_get_tag_list_sends_language_and_version_hash(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TAG_LIST, json=TAG_LIST_REPLY)

    await steam.store.get_tag_list("german", "711684454")

    assert sent(fake_steam.last.query) == {
        "language": "german",
        "have_version_hash": "711684454",
    }


async def test_get_tag_list_parses_real_reply(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TAG_LIST, json=TAG_LIST_REPLY)

    result = await steam.store.get_tag_list()

    assert isinstance(result, TagList)
    assert result.version_hash == "711684454"
    assert len(result.tags) == 6
    strategy, action = result.tags[:2]
    assert isinstance(strategy, StoreTag)
    assert strategy.model_dump() == {"tagid": 9, "name": "Strategy"}
    assert (action.tagid, action.name) == (19, "Action")
    assert result.tags[3].name == "Design & Illustration"


async def test_get_tag_list_unchanged_list_has_no_tags(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TAG_LIST, json={"response": {"version_hash": "711684454"}})

    result = await steam.store.get_tag_list(have_version_hash="711684454")

    assert (result.version_hash, result.tags) == ("711684454", [])


# -- get_user_game_interest_state ---------------------------------------------------


async def test_interest_state_posts_appid_and_token_in_form_body(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", INTEREST_STATE, json=INTEREST_REPLY)

    await steam.store.get_user_game_interest_state(620)

    request = fake_steam.last
    assert sent(request.form) == {"appid": "620", "access_token": ACCESS_TOKEN}
    assert sent(request.query) == {}
    assert API_KEY not in request.body.decode()
    assert "Authorization" not in request.headers


async def test_interest_state_posts_store_and_beta_app_ids(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", INTEREST_STATE, json=INTEREST_REPLY)

    await steam.store.get_user_game_interest_state(
        1091500, store_appid=1091500, beta_appid=2138330
    )

    assert sent(fake_steam.last.form) == {
        "appid": "1091500",
        "store_appid": "1091500",
        "beta_appid": "2138330",
        "access_token": ACCESS_TOKEN,
    }


async def test_interest_state_works_with_access_token_only(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", INTEREST_STATE, json=INTEREST_REPLY)

    await token_only_steam.store.get_user_game_interest_state(620)

    assert sent(fake_steam.last.form) == {"appid": "620", "access_token": ACCESS_TOKEN}


async def test_interest_state_with_api_key_only_raises_before_any_request(
    key_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", INTEREST_STATE, json=INTEREST_REPLY)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await key_only_steam.store.get_user_game_interest_state(620)

    assert fake_steam.requests == []


async def test_interest_state_without_credentials_raises_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", INTEREST_STATE, json=INTEREST_REPLY)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await anonymous_steam.store.get_user_game_interest_state(620)

    assert fake_steam.requests == []


@pytest.mark.parametrize("option", ["appid", "store_appid", "beta_appid"])
@pytest.mark.parametrize("appid", [0, -1, 2**32, True, "620", b"620", 620.0], ids=repr)
async def test_interest_state_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, option: str, appid: Any
) -> None:
    kwargs = {"appid": 620, option: appid}

    with pytest.raises(InvalidAppIDError):
        await steam.store.get_user_game_interest_state(**kwargs)

    assert fake_steam.requests == []


async def test_interest_state_parses_queues_and_playtest_status(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", INTEREST_STATE, json=INTEREST_REPLY)

    result = await steam.store.get_user_game_interest_state(620)

    assert isinstance(result, UserGameInterestState)
    assert result.model_dump() == {
        "owned": False,
        "wishlist": True,
        "ignored": False,
        "following": True,
        "in_queues": [
            EStoreDiscoveryQueueType.COMING_SOON,
            EStoreDiscoveryQueueType.RECOMMENDED,
        ],
        "queues_with_skip": [EStoreDiscoveryQueueType.RECOMMENDED],
        "queue_items_remaining": [12, 7],
        "queue_items_next_appid": [1091500, 1172470],
        "temporarily_owned": False,
        "queues": [
            {
                "type": 1,
                "skipped": False,
                "items_remaining": 12,
                "next_appid": 1091500,
                "experimental_cohort": 0,
            },
            {
                "type": 2,
                "skipped": True,
                "items_remaining": 7,
                "next_appid": 1172470,
                "experimental_cohort": 3,
            },
        ],
        "ignored_reason": 0,
        "beta_status": EPlaytestStatus.INVITED,
    }


async def test_interest_state_defaults_follow_the_proto(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # The New queue (0) and "no playtest" (0) are the declared defaults, so
    # Steam leaves them out.
    body = {"response": {"owned": True, "queues": [{"items_remaining": 3}]}}
    fake_steam.api("POST", INTEREST_STATE, json=body)

    result = await steam.store.get_user_game_interest_state(620)

    assert result.owned is True
    assert result.beta_status == EPlaytestStatus.NONE
    (queue,) = result.queues
    assert isinstance(queue, DiscoveryQueueState)
    assert (queue.type, queue.items_remaining) == (EStoreDiscoveryQueueType.NEW, 3)


@pytest.mark.parametrize(
    ("eresult", "error"),
    [
        pytest.param("8", SteamAPIError, id="invalid-param"),
        pytest.param("15", AuthenticationError, id="access-denied"),
    ],
)
async def test_interest_state_refused_by_steam_raises_with_eresult(
    steam: Steam, fake_steam: FakeSteam, eresult: str, error: type[SteamAPIError]
) -> None:
    fake_steam.api("POST", INTEREST_STATE, json=EMPTY, headers={"x-eresult": eresult})

    with pytest.raises(error) as excinfo:
        await steam.store.get_user_game_interest_state(620)

    assert type(excinfo.value) is error
    assert excinfo.value.eresult == int(eresult)
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


# -- get_package_details ------------------------------------------------------------


async def test_get_package_details_sends_package_id_only_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", PACKAGE_DETAILS, json=PACKAGE_REPLY)

    await steam.store.get_package_details(42467)

    assert sent(fake_steam.last.query) == {"packageids": "42467"}


async def test_get_package_details_sends_country_and_language(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", PACKAGE_DETAILS, json=PACKAGE_REPLY)

    await steam.store.get_package_details(42467, country_code="DE", language="german")

    assert sent(fake_steam.last.query) == {
        "packageids": "42467",
        "cc": "DE",
        "l": "german",
    }


async def test_get_package_details_parses_real_reply(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", PACKAGE_DETAILS, json=PACKAGE_REPLY)

    details = await steam.store.get_package_details(42467)

    assert isinstance(details, PackageDetails)
    assert details.model_dump() == {
        "name": "Europa Universalis IV: Indian Subcontinent Unit Pack",
        "page_image": (
            "https://cdn.akamai.steamstatic.com/steam/subs/42467/header.jpg"
            "?t=1447454201"
        ),
        "header_image": "",
        "small_logo": (
            "https://cdn.akamai.steamstatic.com/steam/subs/42467/capsule_231x87.jpg"
            "?t=1447454201"
        ),
        "page_content": "",
        "apps": [
            {
                "id": 295221,
                "name": "Europa Universalis IV: Indian Subcontinent Unit Pack",
            }
        ],
        "price": {
            "currency": "EUR",
            "initial": 199,
            "final": 199,
            "discount_percent": 0,
            "individual": 0,
        },
        "platforms": {"windows": True, "mac": True, "linux": True},
        "controller": {"full_gamepad": False},
        "release_date": {"coming_soon": False, "date": "16 Jul, 2014"},
    }


async def test_get_package_details_package_without_price(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = {
        "7877": {
            "success": True,
            "data": {"name": "Portal 2 sub", "apps": [{"id": 620, "name": "Portal 2"}]},
        }
    }
    fake_steam.store("GET", PACKAGE_DETAILS, json=body)

    details = await steam.store.get_package_details(7877)

    assert details is not None
    assert details.price is None
    assert [(app.id, app.name) for app in details.apps] == [(620, "Portal 2")]
    assert details.release_date.date == ""


@pytest.mark.parametrize(
    "body",
    [
        {"42467": {"success": False}},
        {"42467": {}},
        {"42467": None},
        {},
        {"1": PACKAGE_REPLY["42467"]},
    ],
    ids=["success-false", "empty-entry", "null-entry", "no-entry", "other-id"],
)
async def test_get_package_details_not_found_gives_none(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.store("GET", PACKAGE_DETAILS, json=body)

    assert await steam.store.get_package_details(42467) is None


@pytest.mark.parametrize("body", ["null", "[]", '"x"'])
async def test_get_package_details_non_object_body_gives_not_found(
    steam: Steam, fake_steam: FakeSteam, body: str
) -> None:
    fake_steam.store("GET", PACKAGE_DETAILS, text=body, content_type="application/json")

    assert await steam.store.get_package_details(42467) is None
    assert await steam.store.get_package_details([42467, 1]) == {}


async def test_get_package_details_several_ids_give_dict_of_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = {**PACKAGE_REPLY, "1": {"success": False}}
    fake_steam.store("GET", PACKAGE_DETAILS, json=body)

    result = await steam.store.get_package_details([42467, 1, 42467])

    # Duplicates are sent once, in order.
    assert sent(fake_steam.last.query) == {"packageids": "42467,1"}
    assert list(result) == [42467]
    assert result[42467].name == (
        "Europa Universalis IV: Indian Subcontinent Unit Pack"
    )


async def test_get_package_details_one_id_in_a_list_gives_dict(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", PACKAGE_DETAILS, json=PACKAGE_REPLY)

    result = await steam.store.get_package_details((42467,))

    assert isinstance(result, dict)
    assert set(result) == {42467}


@pytest.mark.parametrize("packageids", INVALID_PACKAGE_IDS, ids=repr)
async def test_get_package_details_rejects_invalid_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, packageids: Any
) -> None:
    with pytest.raises(ValueError, match="Invalid package id"):
        await steam.store.get_package_details(packageids)

    assert fake_steam.requests == []


async def test_get_package_details_rejects_no_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(ValueError, match="At least one package id"):
        await steam.store.get_package_details([])

    assert fake_steam.requests == []


# -- get_app_reviews ----------------------------------------------------------------


async def test_get_app_reviews_sends_default_filters(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=REVIEWS_REPLY)

    await steam.store.get_app_reviews(REVIEWS_APPID)

    assert sent(fake_steam.last.query) == DEFAULT_REVIEW_PARAMS


async def test_get_app_reviews_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=REVIEWS_REPLY)

    await steam.store.get_app_reviews(
        REVIEWS_APPID,
        filter="recent",
        language="english",
        day_range=30,
        cursor="AoJ4357nuoUDesDy7wM=",
        review_type="negative",
        purchase_type="non_steam_purchase",
        num_per_page=100,
        filter_offtopic_activity=False,
    )

    assert sent(fake_steam.last.query) == {
        "json": "1",
        "filter": "recent",
        "language": "english",
        "cursor": "AoJ4357nuoUDesDy7wM=",
        "review_type": "negative",
        "purchase_type": "non_steam_purchase",
        "num_per_page": "100",
        "day_range": "30",
        "filter_offtopic_activity": "0",
    }


async def test_get_app_reviews_filter_offtopic_activity_true_sends_1(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=REVIEWS_REPLY)

    await steam.store.get_app_reviews(REVIEWS_APPID, filter_offtopic_activity=True)

    assert fake_steam.last.query["filter_offtopic_activity"] == "1"


@pytest.mark.parametrize(
    "cursor",
    ["AoMFQFYshcAAAAAFP+IWQgAAAABw476ZBg==", "AoJ+/a=b&c=d", "a b"],
    ids=["real", "reserved", "space"],
)
async def test_get_app_reviews_url_encodes_cursor(
    steam: Steam, fake_steam: FakeSteam, cursor: str
) -> None:
    # A "+" sent unencoded would arrive as a space, and "&"/"=" would split
    # the parameter.
    fake_steam.store("GET", APP_REVIEWS, json=REVIEWS_REPLY)

    await steam.store.get_app_reviews(REVIEWS_APPID, cursor=cursor)

    assert fake_steam.last.query.getall("cursor") == [cursor]
    assert set(fake_steam.last.query) == set(DEFAULT_REVIEW_PARAMS)


@pytest.mark.parametrize("base", ["/api", "/api/"], ids=["api", "api-trailing-slash"])
async def test_get_app_reviews_goes_to_store_root_not_api(
    fake_steam: FakeSteam, base: str
) -> None:
    settings = make_settings(fake_steam, STEAM_STORE_BASE_URL=fake_steam.url + base)
    fake_steam.add("GET", f"/appreviews/{REVIEWS_APPID}", json=REVIEWS_REPLY)

    async with Steam(api_key=API_KEY, settings=settings) as steam:
        await steam.store.get_app_reviews(REVIEWS_APPID)

    assert [r.path for r in fake_steam.requests] == [f"/appreviews/{REVIEWS_APPID}"]
    assert_no_credential(fake_steam.last)


@pytest.mark.parametrize("appid", INVALID_APP_IDS_M2[:-1], ids=repr)
async def test_get_app_reviews_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appid: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.store.get_app_reviews(appid)

    assert fake_steam.requests == []


async def test_get_app_reviews_parses_real_reply(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=REVIEWS_REPLY)

    result = await steam.store.get_app_reviews(REVIEWS_APPID)

    assert isinstance(result, AppReviews)
    assert result.success == 1
    assert result.cursor == "AoJ4357nuoUDesDy7wM="
    assert result.query_summary.model_dump() == {
        "num_reviews": 14,
        "review_score": EUserReviewScore.NEGATIVE,
        "review_score_desc": "Negative",
        "total_positive": 1,
        "total_negative": 13,
        "total_reviews": 14,
    }
    buggy, short, answered = result.reviews
    assert isinstance(buggy, AppReview)
    assert buggy.model_dump() == {
        "recommendationid": "156911094",
        "author": {
            "steamid": "76561199196119526",
            "num_games_owned": 84,
            "num_reviews": 26,
            "playtime_forever": 90,
            "playtime_last_two_weeks": 0,
            "playtime_at_review": 90,
            "deck_playtime_at_review": 0,
            "last_played": 1676000487,
            "personaname": "",
            "profile_url": "",
        },
        "language": "english",
        "review": "Way to buggy, super laggy.",
        "timestamp_created": 1706319884,
        "timestamp_updated": 1706319884,
        "voted_up": False,
        "votes_up": 0,
        "votes_funny": 0,
        "weighted_vote_score": 0.5,  # a JSON number here
        "comment_count": 0,
        "steam_purchase": True,
        "received_for_free": False,
        "refunded": False,
        "written_during_early_access": True,
        "primarily_steam_deck": False,
        "developer_response": "",
        "timestamp_dev_responded": 0,
        "app_release_date": 0,
        "reactions": [],
    }
    # ... and a JSON string here.
    assert short.weighted_vote_score == pytest.approx(0.532467544078826904)
    assert (short.review, short.votes_up) == ("no", 5)
    assert answered.timestamp_dev_responded == 1672789186
    assert answered.developer_response.startswith("If you could join the discord")


async def test_get_app_reviews_parses_deck_playtime_and_plus_cursor(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=DECK_REVIEWS_REPLY)

    result = await steam.store.get_app_reviews(REVIEWS_APPID)

    assert result.cursor == "AoMFQFYshcAAAAAFP+IWQgAAAABw476ZBg=="
    assert result.query_summary.review_score == EUserReviewScore.OVERWHELMINGLY_POSITIVE
    deck, desktop = result.reviews
    assert deck.author.deck_playtime_at_review == 4194
    assert deck.weighted_vote_score == pytest.approx(0.604918003082275391)
    assert desktop.author.deck_playtime_at_review == 0


async def test_get_app_reviews_parses_newer_fields(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Field names a 2026 probe (cbbsjj0314/picking-my-time-sink) saw in real
    # replies; it redacted the values, so these are illustrative.
    body = {
        "success": 1,
        "query_summary": {"num_reviews": 1},
        "reviews": [
            {
                "recommendationid": "212345678901",
                "author": {
                    "steamid": STEAMID,
                    "personaname": "Gabe",
                    "profile_url": f"https://steamcommunity.com/profiles/{STEAMID}/",
                },
                "app_release_date": "1345568400",
                "refunded": True,
                "reactions": [{"reaction": 1, "count": 2}],
                "weighted_vote_score": 0,
            }
        ],
        "cursor": "AoJ4357nuoUDesDy7wM=",
    }
    fake_steam.store("GET", APP_REVIEWS, json=body)

    (review,) = (await steam.store.get_app_reviews(REVIEWS_APPID)).reviews

    assert review.app_release_date == 1345568400
    assert review.refunded is True
    assert review.reactions == [{"reaction": 1, "count": 2}]
    assert review.author.personaname == "Gabe"
    assert review.author.profile_url.endswith(f"/{STEAMID}/")
    assert review.weighted_vote_score == 0.0


async def test_get_app_reviews_unanswered_query(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Steam's reply for an app it has no reviews for (as stubbed by
    # tamnd/steam-cli; unverified).
    fake_steam.store("GET", APP_REVIEWS, json={"success": 2})

    result = await steam.store.get_app_reviews(REVIEWS_APPID)

    assert result == AppReviews(success=2)


async def test_get_app_reviews_empty_body_gives_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json={})

    assert await steam.store.get_app_reviews(REVIEWS_APPID) == AppReviews()


# -- iter_app_reviews ---------------------------------------------------------------


def review_page(cursor: str, *ids: str) -> dict[str, Any]:
    """A reviews page with reviews ``ids`` and next cursor ``cursor``."""
    return {
        "success": 1,
        "query_summary": {"num_reviews": len(ids)},
        "reviews": [{"recommendationid": i} for i in ids],
        "cursor": cursor,
    }


async def collect(steam: Steam, **kwargs: Any) -> list[str]:
    """The ids of the reviews ``iter_app_reviews`` yields.

    The fake server repeats its last reply, so an iterator that does not stop
    would loop forever; time out instead, so such a bug fails the test.
    """

    async def ids() -> list[str]:
        return [
            review.recommendationid
            async for review in steam.store.iter_app_reviews(REVIEWS_APPID, **kwargs)
        ]

    return await asyncio.wait_for(ids(), timeout=10)


async def test_iter_app_reviews_follows_cursor_until_an_empty_page(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    first, second = "AoMFQFYshcAAAAAFP+IWQgAAAABw476ZBg==", "AoJ4357nuoUDesDy7wM="
    for page in (
        review_page(first, "1", "2"),
        review_page(second, "3"),
        review_page(
            "AoJ0000000000000000=",
        ),
    ):
        fake_steam.store("GET", APP_REVIEWS, json=page)

    assert await collect(steam) == ["1", "2", "3"]

    cursors = [r.query["cursor"] for r in fake_steam.requests]
    assert cursors == ["*", first, second]


async def test_iter_app_reviews_sends_paging_defaults_and_filters(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=review_page("x"))

    await collect(
        steam,
        language="english",
        review_type="positive",
        day_range=7,
        filter_offtopic_activity=False,
    )

    assert sent(fake_steam.last.query) == {
        **DEFAULT_REVIEW_PARAMS,
        "filter": "recent",
        "num_per_page": "100",
        "language": "english",
        "review_type": "positive",
        "day_range": "7",
        "filter_offtopic_activity": "0",
    }


async def test_iter_app_reviews_stops_when_cursor_repeats(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    for page in (
        review_page("A", "1"),
        review_page("B", "2"),
        review_page("A", "3"),
        review_page("C", "4"),
    ):
        fake_steam.store("GET", APP_REVIEWS, json=page)

    assert await collect(steam, filter="all") == ["1", "2", "3"]
    assert [r.query["cursor"] for r in fake_steam.requests] == ["*", "A", "B"]


async def test_iter_app_reviews_stops_when_first_cursor_comes_back(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=review_page("*", "1"))

    assert await collect(steam) == ["1"]
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize("body", [{"success": 2}, review_page("", "1")])
async def test_iter_app_reviews_stops_without_cursor(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=body)

    await collect(steam)

    assert len(fake_steam.requests) == 1


async def test_iter_app_reviews_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(InvalidAppIDError):
        async for _ in steam.store.iter_app_reviews(0):
            pass

    assert fake_steam.requests == []


async def test_iter_app_reviews_raises_api_errors(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=review_page("A", "1"))
    fake_steam.store("GET", APP_REVIEWS, status=500, text="Internal Server Error")
    reviews: list[str] = []

    with pytest.raises(SteamAPIError, match="HTTP 500"):
        async for review in steam.store.iter_app_reviews(REVIEWS_APPID):
            reviews.append(review.recommendationid)

    assert reviews == ["1"]


# -- review fixes: input checks ------------------------------------------------------


async def test_get_community_apps_sends_elanguage_0_for_english(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", COMMUNITY_APPS, json=COMMUNITY_APPS_REPLY)

    await steam.store.get_community_apps(620, language=0)

    assert sent(fake_steam.last.query) == {"appids[0]": "620", "language": "0"}


@pytest.mark.parametrize("language", ["english", "0", True, 1.5, -1, b"6"], ids=repr)
async def test_get_community_apps_rejects_non_elanguage_before_any_request(
    steam: Steam, fake_steam: FakeSteam, language: Any
) -> None:
    # The proto's language is a uint32 (ELanguage); a name like get_tag_list's
    # "english" would otherwise be sent as is.
    with pytest.raises(ValueError, match="ELanguage number"):
        await steam.store.get_community_apps(620, language=language)

    assert fake_steam.requests == []


@pytest.mark.parametrize("option", ["num_per_page", "day_range"])
@pytest.mark.parametrize("value", [True, False, "20", -1, 20.0], ids=repr)
async def test_get_app_reviews_rejects_invalid_counts_before_any_request(
    steam: Steam, fake_steam: FakeSteam, option: str, value: Any
) -> None:
    # A bool would otherwise be sent as "True" / "False".
    with pytest.raises(ValueError, match=f"{option} must be a non-negative int"):
        await steam.store.get_app_reviews(REVIEWS_APPID, **{option: value})

    assert fake_steam.requests == []


async def test_iter_app_reviews_rejects_invalid_count_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(ValueError, match="num_per_page"):
        await collect(steam, num_per_page=True)

    assert fake_steam.requests == []


async def test_get_app_reviews_sends_day_range_0(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", APP_REVIEWS, json=REVIEWS_REPLY)

    await steam.store.get_app_reviews(REVIEWS_APPID, day_range=0)

    assert fake_steam.last.query["day_range"] == "0"
