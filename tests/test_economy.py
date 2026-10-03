"""Tests for the IEconService methods of ``EconomyAPI`` (steam.economy).

- ``get_asset_class_info``: IEconService/GetAssetClassInfo
- ``get_inventory_items_with_descriptions``:
  IEconService/GetInventoryItemsWithDescriptions
- ``get_trade_offers``, ``get_trade_offer``, ``get_trade_offers_summary``,
  ``get_trade_history``, ``get_trade_status``, ``get_trade_hold_durations``:
  the IEconService trade methods

Every method is a GET. GetInventoryItemsWithDescriptions sends the access
token and never the API key; the others send the API key when the client has
one, else the access token. GetAssetClassInfo and
GetInventoryItemsWithDescriptions take nested inputs, sent as one
``input_json`` parameter with 64-bit ids as JSON numbers; the trade methods
take flat inputs.

Fixtures:

- economy_get_trade_offers.json: a real GetTradeOffers reply (Nov 2025),
  verbatim from lewisgibson/go-steam's IEconService test fixtures.
- economy_get_trade_offer.json: one offer and its two item descriptions
  from a real GetTradeOffers reply (Jan 2022) in
  juliarose/steam-tradeoffer-manager, put in GetTradeOffer's
  ``{"offer", "descriptions"}`` shape.
- economy_get_asset_class_info.json: the same two real
  ``CEconItem_Description`` messages in GetAssetClassInfo's shape.
- economy_get_trade_history.json: a real GetTradeHistory reply (Aug 2026),
  verbatim from dmarket/p2p-tracker-core's test fixtures.
- economy_get_trade_status.json: one trade of that history (GetTradeStatus
  answers with the same message).
- economy_get_inventory_items_with_descriptions.json: built from the proto
  with the real CS2 items of a community inventory page published in
  juliarose/steam-tradeoffer-manager; the page's 0/1 flags became the
  proto's booleans.
- economy_get_trade_offers_summary.json and
  economy_get_trade_hold_durations.json: built from the proto.
"""

from __future__ import annotations

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
from steamy_py.models.economy import (
    AssetClassInfo,
    EconInventory,
    EconItemDescription,
    ETradeOfferConfirmationMethod,
    ETradeOfferState,
    Trade,
    TradeHistory,
    TradeHoldDurations,
    TradeOffer,
    TradeOfferDetails,
    TradeOffers,
    TradeOffersSummary,
)
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

ASSET_CLASS_INFO = "/IEconService/GetAssetClassInfo/v1/"
INVENTORY = "/IEconService/GetInventoryItemsWithDescriptions/v1/"
TRADE_OFFERS = "/IEconService/GetTradeOffers/v1/"
TRADE_OFFER = "/IEconService/GetTradeOffer/v1/"
SUMMARY = "/IEconService/GetTradeOffersSummary/v1/"
HISTORY = "/IEconService/GetTradeHistory/v1/"
STATUS = "/IEconService/GetTradeStatus/v1/"
HOLDS = "/IEconService/GetTradeHoldDurations/v1/"

CLASS_INFO_REPLY: dict[str, Any] = load_fixture("economy_get_asset_class_info.json")
INVENTORY_REPLY: dict[str, Any] = load_fixture(
    "economy_get_inventory_items_with_descriptions.json"
)
OFFERS_REPLY: dict[str, Any] = load_fixture("economy_get_trade_offers.json")
OFFER_REPLY: dict[str, Any] = load_fixture("economy_get_trade_offer.json")
SUMMARY_REPLY: dict[str, Any] = load_fixture("economy_get_trade_offers_summary.json")
HISTORY_REPLY: dict[str, Any] = load_fixture("economy_get_trade_history.json")
STATUS_REPLY: dict[str, Any] = load_fixture("economy_get_trade_status.json")
HOLDS_REPLY: dict[str, Any] = load_fixture("economy_get_trade_hold_durations.json")
EMPTY: dict[str, Any] = {"response": {}}

# Classes in economy_get_asset_class_info.json (TF2).
FURNACE = ("237182229", "73651412")  # Battle-Worn Robot Money Furnace
BELT = ("11151781", "2064823791")  # Unusual Trophy Belt
OFFER_ID = "4989854170"  # economy_get_trade_offer.json
TRADE_ID = "723541516341221347"  # economy_get_trade_status.json
PARTNER = "76561198336610283"
# The "token" part of a trade offer URL.
TRADE_TOKEN = "xY2-Ab_c"

INVALID_IDS = [
    pytest.param(True, id="bool"),
    pytest.param(b"12", id="bytes"),
    pytest.param(0, id="zero"),
    pytest.param(-5, id="negative"),
    pytest.param(2**64, id="above-uint64"),
    pytest.param("18446744073709551616", id="above-uint64-str"),
    pytest.param("", id="empty-str"),
    pytest.param("abc", id="not-digits"),
    pytest.param(" 42", id="whitespace"),
    pytest.param("4٢", id="non-ascii-digit"),
    pytest.param(1.5, id="float"),
    pytest.param(None, id="none"),
]

INVALID_APP_IDS = [0, -1, True, 2**32, "440"]

INVALID_STEAMIDS = [
    pytest.param("", id="empty"),
    pytest.param("robinwalker", id="vanity-name"),
    pytest.param(STEAMID[:-1], id="16-digits"),
    pytest.param("103582791429521412", id="group-steamid"),
    pytest.param(True, id="bool"),
    pytest.param(b"76561197960435530", id="bytes"),
]


@dataclass(frozen=True)
class Endpoint:
    """One IEconService request, called with realistic arguments."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    path: str
    reply: dict[str, Any]
    malformed: Any  # JSON that does not fit the method's model
    operation: str  # what the error message says failed
    result_type: type
    auth: str  # "any" or "access_token"

    def serve(self, fake_steam: FakeSteam, **reply: Any) -> None:
        """Register ``reply`` (default: the realistic one) for this method."""
        fake_steam.api("GET", self.path, **(reply or {"json": self.reply}))


ENDPOINTS = [
    Endpoint(
        "get_asset_class_info",
        lambda steam: steam.economy.get_asset_class_info(440, [FURNACE, BELT]),
        ASSET_CLASS_INFO,
        CLASS_INFO_REPLY,
        {"response": {"descriptions": [{"tradable": "sometimes"}]}},
        "get asset class info",
        AssetClassInfo,
        "any",
    ),
    Endpoint(
        "get_inventory_items_with_descriptions",
        lambda steam: steam.economy.get_inventory_items_with_descriptions(
            STEAMID, 730, 2
        ),
        INVENTORY,
        INVENTORY_REPLY,
        {"response": {"assets": {"assetid": "1"}}},
        "get inventory items with descriptions",
        EconInventory,
        "access_token",
    ),
    Endpoint(
        "get_trade_offers",
        lambda steam: steam.economy.get_trade_offers(),
        TRADE_OFFERS,
        OFFERS_REPLY,
        {"response": {"next_cursor": "later"}},
        "get trade offers",
        TradeOffers,
        "any",
    ),
    Endpoint(
        "get_trade_offer",
        lambda steam: steam.economy.get_trade_offer(OFFER_ID),
        TRADE_OFFER,
        OFFER_REPLY,
        {"response": {"offer": [OFFER_ID]}},
        "get trade offer",
        TradeOfferDetails,
        "any",
    ),
    Endpoint(
        "get_trade_offers_summary",
        lambda steam: steam.economy.get_trade_offers_summary(),
        SUMMARY,
        SUMMARY_REPLY,
        {"response": {"pending_received_count": "some"}},
        "get trade offers summary",
        TradeOffersSummary,
        "any",
    ),
    Endpoint(
        "get_trade_history",
        lambda steam: steam.economy.get_trade_history(),
        HISTORY,
        HISTORY_REPLY,
        {"response": {"trades": [{"assets_given": "none"}]}},
        "get trade history",
        TradeHistory,
        "any",
    ),
    Endpoint(
        "get_trade_status",
        lambda steam: steam.economy.get_trade_status(TRADE_ID),
        STATUS,
        STATUS_REPLY,
        {"response": {"trades": {"tradeid": TRADE_ID}}},
        "get trade status",
        TradeHistory,
        "any",
    ),
    Endpoint(
        "get_trade_hold_durations",
        lambda steam: steam.economy.get_trade_hold_durations(PARTNER),
        HOLDS,
        HOLDS_REPLY,
        {"response": {"my_escrow": {"escrow_end_duration_seconds": "long"}}},
        "get trade hold durations",
        TradeHoldDurations,
        "any",
    ),
]
ANY_CREDENTIAL = [e for e in ENDPOINTS if e.auth == "any"]
TOKEN_ONLY = [e for e in ENDPOINTS if e.auth == "access_token"]


def endpoint_params(endpoints: list[Endpoint]) -> Any:
    return pytest.mark.parametrize(
        "endpoint", [pytest.param(endpoint, id=endpoint.name) for endpoint in endpoints]
    )


def sent(pairs: Any) -> dict[str, str]:
    """``pairs`` (a query string) as a dict, checking that no name was sent
    twice."""
    items = list(pairs.items())
    assert len({name for name, _ in items}) == len(items), items
    return dict(items)


def query_without_key(request: RecordedRequest) -> dict[str, str]:
    """The query string of ``request``, minus the API key."""
    inputs = sent(request.query)
    assert inputs.pop("key") == API_KEY
    assert "access_token" not in inputs
    return inputs


def input_json(request: RecordedRequest) -> dict[str, Any]:
    """The decoded ``input_json`` of a service-method request."""
    return json.loads(request.params["input_json"])


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


@pytest.fixture
async def anonymous_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client with no credential at all."""
    async with Steam(settings=settings) as client:
        yield client


# -- every method -------------------------------------------------------------


@endpoint_params(ENDPOINTS)
async def test_call_is_one_get_request_to_v1(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [("GET", endpoint.path)]
    assert fake_steam.last.form == {}


@endpoint_params(ENDPOINTS)
async def test_returns_the_inner_response(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    result = await endpoint.call(steam)

    assert type(result) is endpoint.result_type
    assert result == endpoint.result_type.model_validate(endpoint.reply["response"])


@endpoint_params(ENDPOINTS)
async def test_empty_response_parses_to_defaults(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json=EMPTY)

    result = await endpoint.call(steam)

    assert result == endpoint.result_type()


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


@endpoint_params(ENDPOINTS)
async def test_without_credential_raises_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    with pytest.raises(AuthenticationError):
        await endpoint.call(anonymous_steam)

    assert fake_steam.requests == []


@endpoint_params(ANY_CREDENTIAL)
async def test_sends_only_the_api_key_when_client_has_both(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert fake_steam.last.params["key"] == API_KEY
    assert "access_token" not in fake_steam.last.params


@endpoint_params(ANY_CREDENTIAL)
async def test_sends_the_access_token_without_api_key(
    token_only_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(token_only_steam)

    assert fake_steam.last.params["access_token"] == ACCESS_TOKEN
    assert "key" not in fake_steam.last.params


@endpoint_params(ANY_CREDENTIAL)
async def test_any_credential_message_names_both(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    with pytest.raises(AuthenticationError, match="API key or access token"):
        await endpoint.call(anonymous_steam)


@endpoint_params(TOKEN_ONLY)
async def test_sends_only_the_access_token_when_client_has_both(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert fake_steam.last.params["access_token"] == ACCESS_TOKEN
    assert "key" not in fake_steam.last.params


@endpoint_params(TOKEN_ONLY)
async def test_key_only_client_raises_before_any_request(
    key_only_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await endpoint.call(key_only_steam)

    assert fake_steam.requests == []


# -- get_asset_class_info ---------------------------------------------------------


async def test_get_asset_class_info_sends_classes_as_input_json(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ASSET_CLASS_INFO, json=CLASS_INFO_REPLY)

    await steam.economy.get_asset_class_info(
        440, [FURNACE, (int(BELT[0]), None), 2**64 - 1], language="german"
    )

    assert sorted(query_without_key(fake_steam.last)) == ["input_json"]
    assert input_json(fake_steam.last) == {
        "appid": 440,
        "classes": [
            {"classid": 237182229, "instanceid": 73651412},
            {"classid": 11151781},
            {"classid": 2**64 - 1},
        ],
        "language": "german",
    }


async def test_get_asset_class_info_leaves_language_to_steam_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ASSET_CLASS_INFO, json=CLASS_INFO_REPLY)

    await steam.economy.get_asset_class_info(440, FURNACE[0])

    assert input_json(fake_steam.last) == {
        "appid": 440,
        "classes": [{"classid": 237182229}],
    }


@pytest.mark.parametrize(
    ("classids", "expected"),
    [
        pytest.param(237182229, [{"classid": 237182229}], id="one-int"),
        pytest.param("237182229", [{"classid": 237182229}], id="one-str"),
        pytest.param("0042", [{"classid": 42}], id="leading-zeros"),
        pytest.param(["11", 12], [{"classid": 11}, {"classid": 12}], id="list-of-ids"),
        pytest.param(
            (c for c in ("11", "12")),
            [{"classid": 11}, {"classid": 12}],
            id="generator",
        ),
        pytest.param(
            [("11", "0")], [{"classid": 11, "instanceid": 0}], id="instance-zero"
        ),
        pytest.param([(11, None)], [{"classid": 11}], id="instance-none"),
        # A tuple passed alone is one (classid, instanceid) pair, not two
        # class ids.
        pytest.param(
            FURNACE,
            [{"classid": 237182229, "instanceid": 73651412}],
            id="one-pair-alone",
        ),
        pytest.param((11, None), [{"classid": 11}], id="one-pair-alone-no-instance"),
        pytest.param({"11", "12"}, None, id="set-of-ids"),
    ],
)
async def test_get_asset_class_info_accepts_ids_as_int_or_str(
    steam: Steam, fake_steam: FakeSteam, classids: Any, expected: list[Any]
) -> None:
    fake_steam.api("GET", ASSET_CLASS_INFO, json=EMPTY)

    await steam.economy.get_asset_class_info(440, classids)

    classes = input_json(fake_steam.last)["classes"]
    if expected is None:  # unordered input
        expected = [{"classid": int(classid)} for classid in classids]
        classes = sorted(classes, key=lambda c: c["classid"])
        expected.sort(key=lambda c: c["classid"])
    assert classes == expected


@pytest.mark.parametrize(
    "classids",
    [
        *INVALID_IDS,
        pytest.param([], id="empty-list"),
        pytest.param((), id="empty-tuple"),
        pytest.param([11, False], id="bool-in-list"),
        pytest.param([(11, 12, 13)], id="triple"),
        pytest.param([(11,)], id="single"),
        pytest.param([[11, 12]], id="list-pair"),
        pytest.param([(True, 1)], id="bool-classid"),
        pytest.param([(0, 1)], id="zero-classid"),
        pytest.param([(11, -1)], id="negative-instanceid"),
        pytest.param([(11, "x")], id="text-instanceid"),
        pytest.param([(11, False)], id="bool-instanceid"),
        pytest.param((11, 12, 13), id="triple-alone"),
        pytest.param((11,), id="single-alone"),
        pytest.param({"237182229": "73651412"}, id="mapping"),
    ],
)
async def test_get_asset_class_info_rejects_invalid_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam, classids: Any
) -> None:
    with pytest.raises(ValueError, match=r"class id|instance id|classid"):
        await steam.economy.get_asset_class_info(440, classids)

    assert fake_steam.requests == []


@pytest.mark.parametrize("appid", INVALID_APP_IDS)
async def test_get_asset_class_info_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appid: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.economy.get_asset_class_info(appid, [FURNACE])

    assert fake_steam.requests == []


async def test_get_asset_class_info_parses_descriptions(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ASSET_CLASS_INFO, json=CLASS_INFO_REPLY)

    result = await steam.economy.get_asset_class_info(440, [FURNACE, BELT])

    furnace, belt = result.descriptions
    assert isinstance(belt, EconItemDescription)
    assert (furnace.classid, furnace.instanceid) == FURNACE
    assert furnace.name == "Battle-Worn Robot Money Furnace"
    assert furnace.type == "Level 1 Robot Part"
    assert furnace.commodity is True
    assert furnace.market_actions == []
    assert (belt.appid, belt.classid, belt.instanceid) == (440, *BELT)
    assert belt.name == "Unusual Trophy Belt"
    assert belt.market_hash_name == "Unusual Trophy Belt"
    assert belt.name_color == "8650AC"
    assert belt.background_color == "3C352E"
    assert belt.tradable is True
    assert belt.marketable is True
    assert belt.commodity is False
    assert belt.currency is False
    assert belt.market_tradable_restriction == 7
    assert belt.market_marketable_restriction == 0
    assert belt.full_icon_url is not None
    assert belt.full_icon_url.startswith(
        "https://community.cloudflare.steamstatic.com/economy/image/IzMF03bi9WpSBq"
    )
    assert belt.full_large_icon_url is not None
    assert [(line.type, line.color) for line in belt.descriptions] == [
        ("text", "756b5e"),
        ("text", "ffd700"),
        ("text", ""),
    ]
    assert belt.descriptions[1].value == "★ Unusual Effect: Purple Energy"
    assert [a.name for a in belt.actions] == ["Item Wiki Page...", "Inspect in Game..."]
    (market_action,) = belt.market_actions
    assert market_action.link.startswith("steam://rungame/440/")
    assert [(t.category, t.localized_tag_name, t.color) for t in belt.tags] == [
        ("Quality", "Unusual", "8650AC"),
        ("Type", "Cosmetic", ""),
        ("Class", "Sniper", ""),
    ]
    assert belt.contained_item is None


async def test_item_description_parses_optional_parts() -> None:
    # Parts the fixtures do not show, shaped as CEconItem_Description in
    # SteamDatabase webui/service_econ.proto.
    description = EconItemDescription.model_validate(
        {
            "appid": 730,
            "classid": "5710094579",
            "owner_descriptions": [{"type": "html", "value": "Tradable After ..."}],
            "owner_actions": [{"link": "https://example.invalid", "name": "Use"}],
            "fraudwarnings": ["This item has been renamed."],
            "market_fee": "10",
            "contained_item": {"classid": "1", "name": "Inner", "tradable": True},
            "item_expiration": "2026-12-01T00:00:00Z",
            "market_fee_app": 730,
            "sealed": True,
            "sealed_type": 2,
            "container_properties": {
                "contained_items": [{"classid": "7993064000", "instanceid": "0"}],
                "search_tags": [{"category": "Weapon", "internal_name": "weapon_mp9"}],
            },
            "market_bucket_group_id": "9",
        }
    )

    assert [line.value for line in description.owner_descriptions] == [
        "Tradable After ..."
    ]
    assert description.owner_actions[0].name == "Use"
    assert description.fraudwarnings == ["This item has been renamed."]
    assert description.contained_item is not None
    assert description.contained_item.name == "Inner"
    assert description.contained_item.tradable is True
    assert description.sealed is True
    assert description.sealed_type == 2
    (contained,) = description.container_properties.contained_items
    assert (contained.classid, contained.instanceid) == ("7993064000", "0")
    assert description.container_properties.search_tags[0].internal_name == (
        "weapon_mp9"
    )
    assert description.full_icon_url is None


# -- get_inventory_items_with_descriptions ----------------------------------------


async def test_inventory_sends_defaults_as_input_json(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", INVENTORY, json=INVENTORY_REPLY)

    await steam.economy.get_inventory_items_with_descriptions(STEAMID, 730, 2)

    inputs = sent(fake_steam.last.query)
    assert inputs.pop("access_token") == ACCESS_TOKEN
    assert list(inputs) == ["input_json"]
    assert input_json(fake_steam.last) == {
        "steamid": int(STEAMID),
        "appid": 730,
        "contextid": 2,
        "get_descriptions": True,
        "for_trade_offer_verification": False,
        "language": "english",
        "get_asset_properties": False,
    }


async def test_inventory_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", INVENTORY, json=INVENTORY_REPLY)

    await steam.economy.get_inventory_items_with_descriptions(
        SteamID(STEAMID),
        730,
        "2",
        get_descriptions=False,
        for_trade_offer_verification=True,
        language="german",
        filters={"tradable_only": True, "assetids": [46153215277]},
        start_assetid="46153215276",
        count=500,
        get_asset_properties=True,
    )

    assert input_json(fake_steam.last) == {
        "steamid": int(STEAMID),
        "appid": 730,
        "contextid": 2,
        "get_descriptions": False,
        "for_trade_offer_verification": True,
        "language": "german",
        "get_asset_properties": True,
        "filters": {"tradable_only": True, "assetids": [46153215277]},
        "start_assetid": 46153215276,
        "count": 500,
    }


@pytest.mark.parametrize("steamid", INVALID_STEAMIDS)
async def test_inventory_rejects_invalid_steam_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    with pytest.raises(InvalidSteamIDError):
        await steam.economy.get_inventory_items_with_descriptions(steamid, 730, 2)

    assert fake_steam.requests == []


@pytest.mark.parametrize("appid", INVALID_APP_IDS)
async def test_inventory_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, appid: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.economy.get_inventory_items_with_descriptions(STEAMID, appid, 2)

    assert fake_steam.requests == []


@pytest.mark.parametrize("contextid", INVALID_IDS)
async def test_inventory_rejects_invalid_context_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, contextid: Any
) -> None:
    with pytest.raises(ValueError, match="context id"):
        await steam.economy.get_inventory_items_with_descriptions(
            STEAMID, 730, contextid
        )

    assert fake_steam.requests == []


@pytest.mark.parametrize("start_assetid", [p for p in INVALID_IDS if p.id != "none"])
async def test_inventory_rejects_invalid_start_assetid_before_any_request(
    steam: Steam, fake_steam: FakeSteam, start_assetid: Any
) -> None:
    with pytest.raises(ValueError, match="asset id"):
        await steam.economy.get_inventory_items_with_descriptions(
            STEAMID, 730, 2, start_assetid=start_assetid
        )

    assert fake_steam.requests == []


@pytest.mark.parametrize("count", [0, -1, True, 1.5, "100", 2**31])
async def test_inventory_rejects_invalid_count_before_any_request(
    steam: Steam, fake_steam: FakeSteam, count: Any
) -> None:
    with pytest.raises(ValueError, match="count"):
        await steam.economy.get_inventory_items_with_descriptions(
            STEAMID, 730, 2, count=count
        )

    assert fake_steam.requests == []


async def test_inventory_accepts_the_largest_int32_count(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", INVENTORY, json=EMPTY)

    await steam.economy.get_inventory_items_with_descriptions(
        STEAMID, 730, 2, count=2**31 - 1
    )

    assert input_json(fake_steam.last)["count"] == 2**31 - 1


async def test_inventory_parses_page(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", INVENTORY, json=INVENTORY_REPLY)

    page = await steam.economy.get_inventory_items_with_descriptions(
        STEAMID, 730, 2, get_asset_properties=True
    )

    assert page.more_items is True
    assert page.last_assetid == "46153215276"
    assert page.total_inventory_count == 325
    assert page.missing_assets == []
    first, second = page.assets
    assert (first.appid, first.contextid, first.assetid) == (730, "2", "46153215277")
    assert (first.classid, first.instanceid) == ("6918207757", "302028390")
    assert first.amount == 1
    assert second.assetid == "46153215276"
    mp7, case = page.descriptions
    assert mp7.market_hash_name == "MP7 | Short Ochre (Minimal Wear)"
    assert mp7.tradable and mp7.marketable and not mp7.commodity
    assert mp7.sealed is False
    assert mp7.descriptions[0].name == "exterior_wear"
    assert mp7.descriptions[1].value == ""  # " " (models strip whitespace)
    assert [t.internal_name for t in mp7.tags][:2] == ["CSGO_Type_SMG", "weapon_mp7"]
    assert case.name == "Dreams & Nightmares Case"
    assert case.commodity is True
    (properties,) = page.asset_properties
    assert (properties.appid, properties.contextid, properties.assetid) == (
        730,
        "2",
        "46153215277",
    )
    wear, pattern = properties.asset_properties
    assert wear.propertyid == 2
    assert wear.float_value == pytest.approx(0.111641205847263336)
    assert pattern.propertyid == 1
    assert pattern.int_value == 116
    assert properties.asset_accessories == []


async def test_asset_properties_parse_accessories() -> None:
    # CEconItem_AssetProperties with accessories, shaped from the proto.
    properties = EconInventory.model_validate(
        {
            "missing_assets": [{"appid": 730, "contextid": "2", "assetid": "9"}],
            "asset_properties": [
                {
                    "appid": 730,
                    "contextid": "2",
                    "assetid": "51745566387",
                    "asset_properties": [
                        {"propertyid": 6, "string_value": "C5D576185F2705C4"}
                    ],
                    "asset_accessories": [
                        {
                            "classid": "3",
                            "instanceid": "0",
                            "standalone_properties": [
                                {"propertyid": 1, "int_value": "-4"}
                            ],
                            "nested_accessories": [{"classid": "4"}],
                        }
                    ],
                }
            ],
        }
    )

    assert properties.missing_assets[0].assetid == "9"
    (item,) = properties.asset_properties
    assert item.asset_properties[0].string_value == "C5D576185F2705C4"
    (accessory,) = item.asset_accessories
    assert accessory.classid == "3"
    assert accessory.standalone_properties[0].int_value == -4
    assert accessory.nested_accessories[0].classid == "4"
    assert accessory.parent_relationship_properties == []


# -- get_trade_offers ---------------------------------------------------------------


async def test_get_trade_offers_sends_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TRADE_OFFERS, json=OFFERS_REPLY)

    await steam.economy.get_trade_offers()

    assert query_without_key(fake_steam.last) == {
        "get_sent_offers": "1",
        "get_received_offers": "1",
        "get_descriptions": "0",
        "language": "english",
        "active_only": "1",
        "historical_only": "0",
    }


async def test_get_trade_offers_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TRADE_OFFERS, json=OFFERS_REPLY)

    await steam.economy.get_trade_offers(
        get_sent_offers=False,
        get_received_offers=True,
        get_descriptions=True,
        language="german",
        active_only=False,
        historical_only=True,
        time_historical_cutoff=1762439081,
        cursor=100,
    )

    assert query_without_key(fake_steam.last) == {
        "get_sent_offers": "0",
        "get_received_offers": "1",
        "get_descriptions": "1",
        "language": "german",
        "active_only": "0",
        "historical_only": "1",
        "time_historical_cutoff": "1762439081",
        "cursor": "100",
    }


async def test_get_trade_offers_parses_offers(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TRADE_OFFERS, json=OFFERS_REPLY)

    result = await steam.economy.get_trade_offers()

    assert result.next_cursor == 0
    assert result.descriptions == []
    (sent_offer,) = result.trade_offers_sent
    assert isinstance(sent_offer, TradeOffer)
    assert sent_offer.tradeofferid == "8588538066"
    assert sent_offer.accountid_other == 374860975
    assert sent_offer.steamid_other == SteamID.from_account_id(374860975)
    assert sent_offer.message == ""
    assert sent_offer.trade_offer_state == ETradeOfferState.ACCEPTED
    assert sent_offer.is_our_offer is True
    assert (sent_offer.time_created, sent_offer.time_updated) == (
        1762439081,
        1762439897,
    )
    assert sent_offer.expiration_time == 1763648681
    assert sent_offer.tradeid == "819218913135024606"
    assert sent_offer.confirmation_method == (ETradeOfferConfirmationMethod.MOBILE_APP)
    assert sent_offer.eresult == 1
    assert sent_offer.delay_settlement is True
    assert sent_offer.settlement_date == 1763107200
    assert sent_offer.items_to_receive == []
    (given,) = sent_offer.items_to_give
    assert (given.appid, given.contextid, given.assetid) == (730, "2", "46269328138")
    assert (given.classid, given.instanceid) == ("3213411179", "0")
    assert (given.amount, given.missing, given.est_usd) == (1, True, 185)

    (received,) = result.trade_offers_received
    assert received.tradeofferid == "8588570967"
    assert received.message == "###1253505"
    assert received.trade_offer_state == ETradeOfferState.ACTIVE
    assert received.is_our_offer is False
    assert received.tradeid == ""
    assert received.settlement_date == 0
    assert received.items_to_receive[0].assetid == "47414331877"
    assert received.items_to_receive[0].missing is False


async def test_trade_offer_defaults() -> None:
    offer = TradeOffer()

    assert offer.tradeofferid == ""
    assert offer.eresult == 1  # the proto's declared default
    assert offer.steamid_other is None
    assert offer.items_to_give == offer.items_to_receive == []


def test_trade_offer_enums_match_steamkit() -> None:
    assert [(s.name, s.value) for s in ETradeOfferState] == [
        ("INVALID", 1),
        ("ACTIVE", 2),
        ("ACCEPTED", 3),
        ("COUNTERED", 4),
        ("EXPIRED", 5),
        ("CANCELED", 6),
        ("DECLINED", 7),
        ("INVALID_ITEMS", 8),
        ("CREATED_NEEDS_CONFIRMATION", 9),
        ("CANCELED_BY_SECOND_FACTOR", 10),
        ("IN_ESCROW", 11),
        ("REVERTED", 12),
    ]
    assert [(m.name, m.value) for m in ETradeOfferConfirmationMethod] == [
        ("INVALID", 0),
        ("EMAIL", 1),
        ("MOBILE_APP", 2),
    ]


# -- get_trade_offer ----------------------------------------------------------------


async def test_get_trade_offer_sends_id_and_options(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TRADE_OFFER, json=OFFER_REPLY)

    await steam.economy.get_trade_offer(
        int(OFFER_ID), language="german", get_descriptions=True
    )

    assert query_without_key(fake_steam.last) == {
        "tradeofferid": OFFER_ID,
        "language": "german",
        "get_descriptions": "1",
    }


async def test_get_trade_offer_sends_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TRADE_OFFER, json=OFFER_REPLY)

    await steam.economy.get_trade_offer(OFFER_ID)

    assert query_without_key(fake_steam.last) == {
        "tradeofferid": OFFER_ID,
        "language": "english",
        "get_descriptions": "0",
    }


@pytest.mark.parametrize("tradeofferid", INVALID_IDS)
async def test_get_trade_offer_rejects_invalid_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, tradeofferid: Any
) -> None:
    with pytest.raises(ValueError, match="trade offer id"):
        await steam.economy.get_trade_offer(tradeofferid)

    assert fake_steam.requests == []


async def test_get_trade_offer_parses_offer_and_descriptions(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TRADE_OFFER, json=OFFER_REPLY)

    result = await steam.economy.get_trade_offer(OFFER_ID, get_descriptions=True)

    offer = result.offer
    assert offer.tradeofferid == OFFER_ID
    assert offer.accountid_other == 119913840
    assert offer.message == "hello from rust"
    assert offer.trade_offer_state == ETradeOfferState.CANCELED
    assert offer.is_our_offer is True
    assert offer.escrow_end_date == 0
    assert offer.eresult == 1  # absent from this 2022 reply
    (given,) = offer.items_to_give
    (received,) = offer.items_to_receive
    assert (given.classid, given.instanceid, given.est_usd) == (*FURNACE, 4)
    assert (received.classid, received.instanceid, received.est_usd) == (*BELT, 4700)
    by_class = {(d.classid, d.instanceid): d.name for d in result.descriptions}
    assert by_class == {
        FURNACE: "Battle-Worn Robot Money Furnace",
        BELT: "Unusual Trophy Belt",
    }


# -- get_trade_offers_summary --------------------------------------------------------


async def test_get_trade_offers_summary_sends_no_inputs_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARY, json=SUMMARY_REPLY)

    await steam.economy.get_trade_offers_summary()

    assert query_without_key(fake_steam.last) == {}


async def test_get_trade_offers_summary_sends_time_last_visit(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARY, json=SUMMARY_REPLY)

    await steam.economy.get_trade_offers_summary(time_last_visit=1762439081)

    assert query_without_key(fake_steam.last) == {"time_last_visit": "1762439081"}


async def test_get_trade_offers_summary_parses_counts(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARY, json=SUMMARY_REPLY)

    summary = await steam.economy.get_trade_offers_summary()

    assert summary.pending_received_count == 2
    assert summary.new_received_count == 1
    assert summary.historical_received_count == 31
    assert summary.pending_sent_count == 1
    assert summary.newly_accepted_sent_count == 1
    assert summary.historical_sent_count == 57
    assert summary.escrow_sent_count == 1
    assert summary.provisional == 0


# -- get_trade_history -----------------------------------------------------------------


async def test_get_trade_history_sends_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", HISTORY, json=HISTORY_REPLY)

    await steam.economy.get_trade_history()

    assert query_without_key(fake_steam.last) == {
        "max_trades": "100",
        "navigating_back": "0",
        "get_descriptions": "0",
        "language": "english",
        "include_failed": "0",
        "include_total": "0",
    }


async def test_get_trade_history_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", HISTORY, json=HISTORY_REPLY)

    await steam.economy.get_trade_history(
        max_trades=5,
        start_after_time=1785747967,
        start_after_tradeid=TRADE_ID,
        navigating_back=True,
        get_descriptions=True,
        language="german",
        include_failed=True,
        include_total=True,
    )

    assert query_without_key(fake_steam.last) == {
        "max_trades": "5",
        "start_after_time": "1785747967",
        "start_after_tradeid": TRADE_ID,
        "navigating_back": "1",
        "get_descriptions": "1",
        "language": "german",
        "include_failed": "1",
        "include_total": "1",
    }


@pytest.mark.parametrize("tradeid", [p for p in INVALID_IDS if p.id != "none"])
async def test_get_trade_history_rejects_invalid_trade_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, tradeid: Any
) -> None:
    with pytest.raises(ValueError, match="trade id"):
        await steam.economy.get_trade_history(start_after_tradeid=tradeid)

    assert fake_steam.requests == []


async def test_get_trade_history_parses_trades(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", HISTORY, json=HISTORY_REPLY)

    history = await steam.economy.get_trade_history(max_trades=5)

    assert history.more is True
    assert history.total_trades == 0
    assert history.descriptions == history.devices == []
    assert [t.tradeid for t in history.trades] == [
        "594063027056175076",
        "594063027056175078",
        "731422815690175777",
        "744933614571240779",
        TRADE_ID,
    ]
    rolled_back, _, rollback, _, settling = history.trades
    assert isinstance(rolled_back, Trade)
    assert rolled_back.steamid_other == PARTNER
    assert rolled_back.time_init == 1785760511
    assert rolled_back.status == 3
    assert rolled_back.rollback_trade == "731422815690175777"
    assert rolled_back.assets_received == []
    (given,) = rolled_back.assets_given
    assert (given.appid, given.contextid, given.assetid) == (730, "2", "51978272357")
    assert given.amount == 0  # left out of this reply
    assert (rollback.status, rollback.time_mod) == (12, 1785760511)
    assert rollback.rollback_trade == ""
    assert settling.steamid_other == "76561199497281579"
    assert settling.time_settlement == 1786356000
    assert settling.trade_auth.is_sender is False


async def test_trade_history_parses_optional_parts() -> None:
    # Parts the fixture does not show, shaped as CEcon_GetTradeHistory_Response
    # in SteamDatabase webui/service_econ.proto: 64-bit ids and amounts
    # arrive as strings.
    history = TradeHistory.model_validate(
        {
            "total_trades": 88,
            "trades": [
                {
                    "tradeid": "3622544162294464626",
                    "time_escrow_end": 1700000000,
                    "assets_received": [
                        {
                            "appid": 440,
                            "contextid": "2",
                            "assetid": "9443876106",
                            "amount": "1",
                            "classid": "5564",
                            "instanceid": "11040547",
                            "new_assetid": "9443900000",
                            "new_contextid": "2",
                        }
                    ],
                    "currency_given": [
                        {
                            "appid": 753,
                            "contextid": "6",
                            "currencyid": 1,
                            "amount": "250",
                            "fee_amount": "25",
                            "new_currencyid": 2,
                        }
                    ],
                    "trade_auth": {
                        "is_sender": True,
                        "confirm_type": 2,
                        "time_confirmed": 1700000100,
                        "country": "DE",
                        "token_id": "18446744073709551615",
                    },
                }
            ],
            "descriptions": [{"classid": "5564", "name": "Scrap Metal"}],
            "devices": [
                {
                    "token_id": "18446744073709551615",
                    "first_authed": 1600000000,
                    "current_device": True,
                    "platform_type": 2,
                }
            ],
        }
    )

    assert history.total_trades == 88
    (trade,) = history.trades
    assert trade.time_escrow_end == 1700000000
    (asset,) = trade.assets_received
    assert (asset.amount, asset.new_assetid, asset.new_contextid) == (
        1,
        "9443900000",
        "2",
    )
    (currency,) = trade.currency_given
    assert (currency.amount, currency.fee_amount, currency.new_currencyid) == (
        250,
        25,
        2,
    )
    assert trade.trade_auth.is_sender is True
    assert trade.trade_auth.country == "DE"
    assert trade.trade_auth.token_id == "18446744073709551615"
    assert history.descriptions[0].name == "Scrap Metal"
    (device,) = history.devices
    assert device.current_device is True
    assert device.token_id == "18446744073709551615"


# -- get_trade_status -----------------------------------------------------------------


async def test_get_trade_status_sends_id_and_options(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STATUS, json=STATUS_REPLY)

    await steam.economy.get_trade_status(
        int(TRADE_ID), get_descriptions=True, language="german"
    )

    assert query_without_key(fake_steam.last) == {
        "tradeid": TRADE_ID,
        "get_descriptions": "1",
        "language": "german",
    }


async def test_get_trade_status_sends_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STATUS, json=STATUS_REPLY)

    await steam.economy.get_trade_status(TRADE_ID)

    assert query_without_key(fake_steam.last) == {
        "tradeid": TRADE_ID,
        "get_descriptions": "0",
        "language": "english",
    }


@pytest.mark.parametrize("tradeid", INVALID_IDS)
async def test_get_trade_status_rejects_invalid_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, tradeid: Any
) -> None:
    with pytest.raises(ValueError, match="trade id"):
        await steam.economy.get_trade_status(tradeid)

    assert fake_steam.requests == []


async def test_get_trade_status_parses_trade(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STATUS, json=STATUS_REPLY)

    result = await steam.economy.get_trade_status(TRADE_ID)

    (trade,) = result.trades
    assert trade.tradeid == TRADE_ID
    assert trade.status == 3
    assert trade.time_init == 1785747967
    assert trade.time_settlement == 1786356000
    assert [a.assetid for a in trade.assets_given] == ["50520000968"]
    assert result.more is False


# -- get_trade_hold_durations --------------------------------------------------------


async def test_get_trade_hold_durations_sends_partner_and_token(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", HOLDS, json=HOLDS_REPLY)

    await steam.economy.get_trade_hold_durations(
        SteamID(PARTNER), trade_offer_access_token=TRADE_TOKEN
    )

    assert query_without_key(fake_steam.last) == {
        "steamid_target": PARTNER,
        "trade_offer_access_token": TRADE_TOKEN,
    }


async def test_get_trade_hold_durations_without_trade_token(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", HOLDS, json=HOLDS_REPLY)

    await steam.economy.get_trade_hold_durations(int(PARTNER))

    assert query_without_key(fake_steam.last) == {"steamid_target": PARTNER}


async def test_trade_token_is_kept_next_to_the_access_token(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", HOLDS, json=HOLDS_REPLY)

    await token_only_steam.economy.get_trade_hold_durations(
        PARTNER, trade_offer_access_token=TRADE_TOKEN
    )

    assert sent(fake_steam.last.query) == {
        "steamid_target": PARTNER,
        "trade_offer_access_token": TRADE_TOKEN,
        "access_token": ACCESS_TOKEN,
    }


@pytest.mark.parametrize("steamid", INVALID_STEAMIDS)
async def test_get_trade_hold_durations_rejects_invalid_steam_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    with pytest.raises(InvalidSteamIDError):
        await steam.economy.get_trade_hold_durations(steamid)

    assert fake_steam.requests == []


async def test_get_trade_hold_durations_parses_holds(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", HOLDS, json=HOLDS_REPLY)

    holds = await steam.economy.get_trade_hold_durations(PARTNER)

    assert holds.my_escrow.escrow_end_duration_seconds == 0
    assert holds.my_escrow.escrow_end_date == 0
    assert holds.my_escrow.escrow_end_date_rfc3339 == ""
    assert holds.their_escrow.escrow_end_duration_seconds == 15 * 24 * 3600
    assert holds.their_escrow.escrow_end_date == 1775563200
    assert holds.their_escrow.escrow_end_date_rfc3339 == "2026-04-07T12:00:00Z"
    assert holds.both_escrow == holds.their_escrow
