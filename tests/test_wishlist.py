"""Tests for ``WishlistAPI``: IWishlistService/GetWishlist and GetWishlistItemCount.

Both methods take only a Steam ID and need no credential, so the client must
not send one even when it has them. The reply fixtures follow
``CWishlist_GetWishlist_Response`` and ``CWishlist_GetWishlistItemCount_Response``
(SteamDatabase/Protobufs, webui/service_wishlist.proto) and the shape of a
recorded GetWishlist reply: items in app id order, ranks from 1 with gaps, and
an explicit ``"priority": 0`` for an app without a rank.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from steamy_py import (
    InvalidSteamIDError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
    SteamID,
)
from steamy_py.models.wishlist import Wishlist, WishlistItem
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

LOGIN_COOKIE = "76561197960435530%7C%7Ctest-login-cookie"

WISHLIST: dict[str, Any] = load_fixture("wishlist_get_wishlist.json")
ITEM_COUNT: dict[str, Any] = load_fixture("wishlist_get_wishlist_item_count.json")


@dataclass(frozen=True)
class Endpoint:
    """One ``WishlistAPI`` method."""

    name: str
    call: Callable[[Steam, Any], Awaitable[Any]]
    rpc: str
    reply: dict[str, Any]

    @property
    def path(self) -> str:
        return f"/IWishlistService/{self.rpc}/v1/"


ENDPOINTS = [
    Endpoint(
        "get_wishlist",
        lambda steam, steamid: steam.wishlist.get_wishlist(steamid),
        "GetWishlist",
        WISHLIST,
    ),
    Endpoint(
        "get_wishlist_item_count",
        lambda steam, steamid: steam.wishlist.get_wishlist_item_count(steamid),
        "GetWishlistItemCount",
        ITEM_COUNT,
    ),
]

ENDPOINT_PARAMS = [pytest.param(endpoint, id=endpoint.name) for endpoint in ENDPOINTS]


def assert_no_credential(request: RecordedRequest) -> None:
    """Check that ``request`` carries no key, access token or cookie."""
    assert "key" not in request.query
    assert "access_token" not in request.query
    assert "Cookie" not in request.headers
    assert "Authorization" not in request.headers


@pytest.fixture
async def credentialed_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client holding every credential the library supports."""
    async with Steam(
        api_key=API_KEY,
        access_token=ACCESS_TOKEN,
        steam_login_secure=LOGIN_COOKIE,
        settings=settings,
    ) as client:
        yield client


@pytest.fixture
async def anonymous_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client without any credential."""
    async with Steam(settings=settings) as client:
        yield client


# -- requests ----------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
async def test_call_uses_get_and_v1(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api("GET", endpoint.path, json=endpoint.reply)

    await endpoint.call(steam, STEAMID)

    assert len(fake_steam.requests) == 1
    assert (fake_steam.last.method, fake_steam.last.path) == ("GET", endpoint.path)


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
async def test_call_sends_only_the_steamid_and_no_credential(
    credentialed_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api("GET", endpoint.path, json=endpoint.reply)

    await endpoint.call(credentialed_steam, STEAMID)

    assert fake_steam.last.params == {"steamid": STEAMID}
    assert_no_credential(fake_steam.last)


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
async def test_call_works_without_any_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api("GET", endpoint.path, json=endpoint.reply)

    await endpoint.call(anonymous_steam, STEAMID)

    assert fake_steam.last.params == {"steamid": STEAMID}


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param(int(STEAMID), id="int"),
        pytest.param(STEAMID, id="str"),
        pytest.param(SteamID(STEAMID), id="SteamID"),
    ],
)
async def test_call_accepts_steamid_as_int_str_or_steamid(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint, steamid: Any
) -> None:
    fake_steam.api("GET", endpoint.path, json=endpoint.reply)

    await endpoint.call(steam, steamid)

    assert fake_steam.last.params["steamid"] == STEAMID


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param("", id="empty"),
        pytest.param("gabelogannewell", id="vanity-name"),
        pytest.param(22202, id="account-id"),
        pytest.param("103582791429521408", id="group-id"),
        pytest.param(True, id="bool"),
    ],
)
async def test_invalid_steamid_is_rejected_before_any_request(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint, steamid: Any
) -> None:
    fake_steam.api("GET", endpoint.path, json=endpoint.reply)

    with pytest.raises(InvalidSteamIDError):
        await endpoint.call(steam, steamid)

    assert fake_steam.requests == []


# -- errors ------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
async def test_http_500_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api("GET", endpoint.path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError, match="HTTP 500") as excinfo:
        await endpoint.call(steam, STEAMID)

    assert excinfo.value.status_code == 500


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        pytest.param(ENDPOINTS[0], {"response": {"items": 1}}, id="items-not-a-list"),
        pytest.param(
            ENDPOINTS[0],
            {"response": {"items": [{"appid": "Half-Life 3"}]}},
            id="appid-not-a-number",
        ),
        pytest.param(ENDPOINTS[0], {"response": []}, id="wishlist-response-a-list"),
        pytest.param(ENDPOINTS[1], {"response": {"count": "many"}}, id="count-text"),
        pytest.param(ENDPOINTS[1], [], id="count-body-a-list"),
    ],
)
async def test_malformed_response_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint, body: Any
) -> None:
    fake_steam.api("GET", endpoint.path, json=body)

    operation = endpoint.name.replace("_", " ")
    with pytest.raises(ResponseParsingError, match=f"Failed to {operation}:"):
        await endpoint.call(steam, STEAMID)


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
async def test_non_json_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api(
        "GET",
        endpoint.path,
        text="<html><body>Service Unavailable</body></html>",
        content_type="text/html",
    )

    with pytest.raises(ResponseParsingError, match="Invalid JSON response"):
        await endpoint.call(steam, STEAMID)


# -- GetWishlist ---------------------------------------------------------------------


async def test_get_wishlist_parses_items(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", ENDPOINTS[0].path, json=WISHLIST)

    wishlist = await steam.wishlist.get_wishlist(STEAMID)

    assert isinstance(wishlist, Wishlist)
    assert wishlist.items == [
        WishlistItem(appid=413150, priority=3, date_added=1651363200),
        WishlistItem(appid=1086940, priority=0, date_added=1760054400),
        WishlistItem(appid=1245620, priority=1, date_added=1689811200),
    ]


async def test_get_wishlist_returns_empty_wishlist_for_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # A private (or empty) wishlist: Steam leaves out the empty item list.
    fake_steam.api("GET", ENDPOINTS[0].path, json={"response": {}})

    wishlist = await steam.wishlist.get_wishlist(STEAMID)

    assert wishlist == Wishlist(items=[])


async def test_get_wishlist_fills_in_omitted_item_fields(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ENDPOINTS[0].path, json={"response": {"items": [{}]}})

    wishlist = await steam.wishlist.get_wishlist(STEAMID)

    assert wishlist.items == [WishlistItem(appid=0, priority=0, date_added=0)]


async def test_get_wishlist_ignores_fields_it_does_not_know(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = {"response": {"items": [{"appid": 620, "category_ids": ["7"]}], "x": 1}}
    fake_steam.api("GET", ENDPOINTS[0].path, json=body)

    wishlist = await steam.wishlist.get_wishlist(STEAMID)

    assert [item.appid for item in wishlist.items] == [620]


# -- GetWishlistItemCount ------------------------------------------------------------


async def test_get_wishlist_item_count_returns_count(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ENDPOINTS[1].path, json=ITEM_COUNT)

    assert await steam.wishlist.get_wishlist_item_count(STEAMID) == 3


async def test_get_wishlist_item_count_is_zero_when_count_is_omitted(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ENDPOINTS[1].path, json={"response": {}})

    assert await steam.wishlist.get_wishlist_item_count(STEAMID) == 0
