"""Tests for the keyless store search and item methods of ``StoreAPI``.

- ``get_items``: IStoreBrowseService/GetItems
- ``search_suggestions``: IStoreQueryService/SearchSuggestions
- ``store_search``: store.steampowered.com/api/storesearch

None of them needs a credential, so none may be sent. Both service methods
take nested inputs, sent as one ``input_json`` parameter.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from steamy_py import (
    InvalidAppIDError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
)
from steamy_py.models.store import (
    ESteamDeckCompatibilityCategory,
    EStoreAppType,
    EStoreItemType,
    EUserReviewScore,
    SearchSuggestions,
    StoreItem,
    StoreItems,
    StoreSearchResult,
)
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
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
