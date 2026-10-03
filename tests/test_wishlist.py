"""Tests for ``steam.wishlist`` (IWishlistService): reading wishlists, and adding
to and removing from the signed-in user's wishlist.

GetWishlist and GetWishlistItemCount take only a Steam ID and need no
credential, so the client must not send one even when it has them. The reply
fixtures follow ``CWishlist_GetWishlist_Response`` and
``CWishlist_GetWishlistItemCount_Response`` (SteamDatabase/Protobufs,
webui/service_wishlist.proto) and the shape of a
recorded GetWishlist reply: items in app id order, ranks from 1 with gaps, and
an explicit ``"priority": 0`` for an app without a rank.

The other methods are tested at the end of the file:

- ``add_to_wishlist`` / ``remove_from_wishlist``: AddToWishlist and
  RemoveFromWishlist, POST writes that send only the access token
- ``get_wishlist_items_on_sale``: GetWishlistItemsOnSale, GET with the access
  token and an ``input_json`` input
- ``get_wishlist_sorted_filtered``: GetWishlistSortedFiltered, keyless GET with
  an ``input_json`` input

No recorded replies of these methods were found, so their fixtures are built
from the proto response messages. The store item inside them is the Portal 2
``StoreItem`` of store_get_items.json, cut to the parts a request with only
``include_basic_info`` asks for (plus ``best_purchase_option``, which the
data request includes by default).
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
from steamy_py.models.store import StoreItem
from steamy_py.models.wishlist import (
    Wishlist,
    WishlistItem,
    WishlistItemsOnSale,
    WishlistSortedFiltered,
    WishlistSortedItem,
)
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


# == Milestone 2 ======================================================================

ADD_PATH = "/IWishlistService/AddToWishlist/v1/"
REMOVE_PATH = "/IWishlistService/RemoveFromWishlist/v1/"
ON_SALE_PATH = "/IWishlistService/GetWishlistItemsOnSale/v1/"
SORTED_PATH = "/IWishlistService/GetWishlistSortedFiltered/v1/"

ADDED: dict[str, Any] = load_fixture("wishlist_add_to_wishlist.json")
REMOVED: dict[str, Any] = load_fixture("wishlist_remove_from_wishlist.json")
ON_SALE: dict[str, Any] = load_fixture("wishlist_get_wishlist_items_on_sale.json")
SORTED: dict[str, Any] = load_fixture("wishlist_get_wishlist_sorted_filtered.json")
EMPTY: dict[str, Any] = {"response": {}}

US_ENGLISH = {"language": "english", "country_code": "US", "steam_realm": 1}
INVALID_APP_IDS = [
    pytest.param(0, id="zero"),
    pytest.param(-1, id="negative"),
    pytest.param(2**32, id="above-uint32"),
    pytest.param(True, id="bool"),
    pytest.param("620", id="str"),
    pytest.param(None, id="none"),
]


@dataclass(frozen=True)
class Call:
    """One Milestone 2 ``WishlistAPI`` request, made with realistic arguments."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    verb: str
    path: str
    reply: dict[str, Any]
    malformed: Any  # JSON that does not fit the method's model
    operation: str  # what the error message says failed


CALLS = [
    Call(
        "add_to_wishlist",
        lambda steam: steam.wishlist.add_to_wishlist(620),
        "POST",
        ADD_PATH,
        ADDED,
        {"response": {"wishlist_count": "many"}},
        "add to wishlist",
    ),
    Call(
        "remove_from_wishlist",
        lambda steam: steam.wishlist.remove_from_wishlist(620),
        "POST",
        REMOVE_PATH,
        REMOVED,
        {"response": []},
        "remove from wishlist",
    ),
    Call(
        "get_wishlist_items_on_sale",
        lambda steam: steam.wishlist.get_wishlist_items_on_sale(),
        "GET",
        ON_SALE_PATH,
        ON_SALE,
        {"response": {"items": [{"appid": 620, "store_item": []}]}},
        "get wishlist items on sale",
    ),
    Call(
        "get_wishlist_sorted_filtered",
        lambda steam: steam.wishlist.get_wishlist_sorted_filtered(STEAMID),
        "GET",
        SORTED_PATH,
        SORTED,
        {"response": {"items": [{"appid": 620, "category_ids": "1"}]}},
        "get wishlist sorted filtered",
    ),
]
WRITE_CALLS = CALLS[:2]
TOKEN_CALLS = CALLS[:3]  # the methods about the signed-in user


def call_params(calls: list[Call]) -> Any:
    return pytest.mark.parametrize(
        "call", [pytest.param(call, id=call.name) for call in calls]
    )


def sent(pairs: Any) -> dict[str, str]:
    """``pairs`` (a query string or form body) as a dict, checking that no
    name was sent twice."""
    items = list(pairs.items())
    assert len({name for name, _ in items}) == len(items), items
    return dict(items)


def sent_input_json(request: RecordedRequest) -> Any:
    """The decoded ``input_json`` parameter of a GET request."""
    return json.loads(request.query["input_json"])


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


# -- every Milestone 2 method ------------------------------------------------------


@call_params(CALLS)
async def test_m2_call_is_one_request_with_documented_verb_and_path(
    steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(call.verb, call.path, json=call.reply)

    await call.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [(call.verb, call.path)]


@call_params(CALLS)
async def test_m2_http_500_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(call.verb, call.path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await call.call(steam)

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == 500
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@call_params(CALLS)
async def test_m2_malformed_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(call.verb, call.path, json=call.malformed)

    with pytest.raises(ResponseParsingError, match=f"Failed to {call.operation}:"):
        await call.call(steam)


@call_params(CALLS)
async def test_m2_body_that_is_not_an_object_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(call.verb, call.path, json=[])

    with pytest.raises(ResponseParsingError, match=f"Failed to {call.operation}:"):
        await call.call(steam)


@call_params(CALLS)
async def test_m2_non_json_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(
        call.verb, call.path, text="<html>Error</html>", content_type="text/html"
    )

    with pytest.raises(ResponseParsingError, match="Invalid JSON response"):
        await call.call(steam)


@call_params(TOKEN_CALLS)
async def test_signed_in_user_methods_send_only_the_access_token(
    steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(call.verb, call.path, json=call.reply)

    await call.call(steam)

    request = fake_steam.last
    inputs = sent(request.form if call.verb == "POST" else request.query)
    assert inputs["access_token"] == ACCESS_TOKEN
    assert "key" not in inputs
    assert API_KEY.encode() not in request.body
    assert "Cookie" not in request.headers
    assert "Authorization" not in request.headers


@call_params(TOKEN_CALLS)
async def test_signed_in_user_methods_work_with_only_an_access_token(
    token_only_steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(call.verb, call.path, json=call.reply)

    await call.call(token_only_steam)

    request = fake_steam.last
    inputs = sent(request.form if call.verb == "POST" else request.query)
    assert inputs["access_token"] == ACCESS_TOKEN


@call_params(TOKEN_CALLS)
async def test_signed_in_user_methods_need_the_access_token_not_the_key(
    key_only_steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(call.verb, call.path, json=call.reply)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await call.call(key_only_steam)

    assert fake_steam.requests == []


@call_params(TOKEN_CALLS)
async def test_signed_in_user_methods_without_credential_raise_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.add(call.verb, call.path, json=call.reply)

    with pytest.raises(AuthenticationError):
        await call.call(anonymous_steam)

    assert fake_steam.requests == []


# -- add_to_wishlist / remove_from_wishlist ------------------------------------------


@call_params(WRITE_CALLS)
async def test_write_posts_appid_and_token_in_form_body(
    steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    fake_steam.api("POST", call.path, json=call.reply)

    await call.call(steam)

    request = fake_steam.last
    assert sent(request.form) == {"appid": "620", "access_token": ACCESS_TOKEN}
    assert sent(request.query) == {}


async def test_add_to_wishlist_returns_wishlist_count(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", ADD_PATH, json=ADDED)

    assert await steam.wishlist.add_to_wishlist(620) == 4


async def test_remove_from_wishlist_returns_wishlist_count(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", REMOVE_PATH, json=REMOVED)

    assert await steam.wishlist.remove_from_wishlist(620) == 3


@call_params(WRITE_CALLS)
async def test_write_returns_zero_when_count_is_omitted(
    steam: Steam, fake_steam: FakeSteam, call: Call
) -> None:
    # The count is 0 when the wishlist ends up empty: protobuf leaves it out.
    fake_steam.api("POST", call.path, json=EMPTY)

    assert await call.call(steam) == 0


async def test_add_to_wishlist_sends_navdata_as_input_json(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", ADD_PATH, json=ADDED)
    navdata = {"domain": "store.steampowered.com", "controller": "app", "depth": 1}

    count = await steam.wishlist.add_to_wishlist(620, navdata=navdata)

    form = sent(fake_steam.last.form)
    assert form.pop("access_token") == ACCESS_TOKEN
    assert list(form) == ["input_json"]
    assert json.loads(form["input_json"]) == {"appid": 620, "navdata": navdata}
    assert count == 4


@pytest.mark.parametrize(
    ("method", "path"),
    [("add_to_wishlist", ADD_PATH), ("remove_from_wishlist", REMOVE_PATH)],
)
@pytest.mark.parametrize("appid", INVALID_APP_IDS)
async def test_write_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, method: str, path: str, appid: Any
) -> None:
    fake_steam.api("POST", path, json=ADDED)

    with pytest.raises(InvalidAppIDError):
        await getattr(steam.wishlist, method)(appid)

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    ("eresult", "error"),
    [
        pytest.param("8", SteamAPIError, id="invalid-param"),
        pytest.param("15", AuthenticationError, id="access-denied"),
    ],
)
@call_params(WRITE_CALLS)
async def test_write_refused_by_steam_raises_with_eresult(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    eresult: str,
    error: type[SteamAPIError],
) -> None:
    fake_steam.api("POST", call.path, json=EMPTY, headers={"x-eresult": eresult})

    with pytest.raises(error) as excinfo:
        await call.call(steam)

    assert type(excinfo.value) is error
    assert excinfo.value.eresult == int(eresult)
    assert ACCESS_TOKEN not in str(excinfo.value)
    # A POST that Steam refused is not repeated.
    assert len(fake_steam.requests) == 1


# -- get_wishlist_items_on_sale ------------------------------------------------------


async def test_items_on_sale_sends_context_and_basic_info_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ON_SALE_PATH, json=ON_SALE)

    await steam.wishlist.get_wishlist_items_on_sale()

    request = fake_steam.last
    assert set(sent(request.query)) == {"input_json", "access_token"}
    assert sent_input_json(request) == {
        "context": US_ENGLISH,
        "data_request": {"include_basic_info": True},
    }


async def test_items_on_sale_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ON_SALE_PATH, json=ON_SALE)

    await steam.wishlist.get_wishlist_items_on_sale(
        language="german",
        country_code="DE",
        include_basic_info=True,
        include_assets=True,
        include_release=True,
        include_platforms=True,
        include_reviews=True,
        include_all_purchase_options=True,
        include_tag_count=5,
    )

    assert sent_input_json(fake_steam.last) == {
        "context": {"language": "german", "country_code": "DE", "steam_realm": 1},
        "data_request": {
            "include_basic_info": True,
            "include_assets": True,
            "include_release": True,
            "include_platforms": True,
            "include_reviews": True,
            "include_all_purchase_options": True,
            "include_tag_count": 5,
        },
    }


async def test_items_on_sale_without_store_data_sends_no_data_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ON_SALE_PATH, json=ON_SALE)

    await steam.wishlist.get_wishlist_items_on_sale(include_basic_info=False)

    assert sent_input_json(fake_steam.last) == {"context": US_ENGLISH}


async def test_items_on_sale_parses_items(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", ON_SALE_PATH, json=ON_SALE)

    result = await steam.wishlist.get_wishlist_items_on_sale()

    assert isinstance(result, WishlistItemsOnSale)
    assert result.total_items_on_sale == 1
    (item,) = result.items
    assert item.appid == 620
    store_item = item.store_item
    assert isinstance(store_item, StoreItem)
    assert (store_item.appid, store_item.name) == (620, "Portal 2")
    assert store_item.success == 1 and store_item.visible
    assert [d.name for d in store_item.basic_info.developers] == ["Valve"]
    offer = store_item.best_purchase_option
    assert offer.packageid == 7877
    assert (offer.final_price_in_cents, offer.original_price_in_cents) == (199, 999)
    assert offer.discount_pct == 80
    assert offer.formatted_final_price == "$1.99"
    assert offer.active_discounts[0].discount_end_date == 1760029200
    # Parts the data request did not ask for keep their defaults.
    assert store_item.assets.header == ""
    assert store_item.purchase_options == []


async def test_items_on_sale_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Nothing on sale: protobuf leaves out the empty list and the zero count.
    fake_steam.api("GET", ON_SALE_PATH, json=EMPTY)

    result = await steam.wishlist.get_wishlist_items_on_sale()

    assert result == WishlistItemsOnSale(items=[], total_items_on_sale=0)


# -- get_wishlist_sorted_filtered ----------------------------------------------------


async def test_sorted_filtered_sends_no_credential(
    credentialed_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=SORTED)

    await credentialed_steam.wishlist.get_wishlist_sorted_filtered(STEAMID)

    request = fake_steam.last
    assert set(sent(request.query)) == {"input_json"}
    assert_no_credential(request)


async def test_sorted_filtered_works_without_any_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=SORTED)

    result = await anonymous_steam.wishlist.get_wishlist_sorted_filtered(STEAMID)

    assert [item.appid for item in result.items] == [620, 440]


async def test_sorted_filtered_sends_steamid_context_and_data_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=SORTED)

    await steam.wishlist.get_wishlist_sorted_filtered(STEAMID)

    assert sent_input_json(fake_steam.last) == {
        "steamid": STEAMID,
        "context": US_ENGLISH,
        "data_request": {"include_basic_info": True},
    }


async def test_sorted_filtered_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=SORTED)
    filters = {
        "min_discount_percent": 50,
        "only_games": True,
        "exclude_types": {"exclude_early_access": True},
        "tagids_must_match": [19],
    }

    await steam.wishlist.get_wishlist_sorted_filtered(
        int(STEAMID),
        sort_order=5,
        filters=filters,
        start_index=20,
        page_size=10,
        share_token="token-from-a-shared-link",
        language="french",
        country_code="FR",
        include_basic_info=False,
        include_assets=True,
        include_release=True,
        include_platforms=True,
        include_reviews=True,
        include_all_purchase_options=True,
        include_tag_count=20,
    )

    assert sent_input_json(fake_steam.last) == {
        "steamid": STEAMID,
        "context": {"language": "french", "country_code": "FR", "steam_realm": 1},
        "data_request": {
            "include_assets": True,
            "include_release": True,
            "include_platforms": True,
            "include_reviews": True,
            "include_all_purchase_options": True,
            "include_tag_count": 20,
        },
        "sort_order": 5,
        "filters": filters,
        "start_index": 20,
        "page_size": 10,
        "share_token": "token-from-a-shared-link",
    }


async def test_sorted_filtered_without_store_data_sends_no_data_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=SORTED)

    await steam.wishlist.get_wishlist_sorted_filtered(
        STEAMID, include_basic_info=False, start_index=0
    )

    assert sent_input_json(fake_steam.last) == {
        "steamid": STEAMID,
        "context": US_ENGLISH,
        "start_index": 0,
    }


@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param(int(STEAMID), id="int"),
        pytest.param(STEAMID, id="str"),
        pytest.param(SteamID(STEAMID), id="SteamID"),
    ],
)
async def test_sorted_filtered_accepts_steamid_as_int_str_or_steamid(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=SORTED)

    await steam.wishlist.get_wishlist_sorted_filtered(steamid)

    assert sent_input_json(fake_steam.last)["steamid"] == STEAMID


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
async def test_sorted_filtered_rejects_invalid_steamid_before_any_request(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=SORTED)

    with pytest.raises(InvalidSteamIDError):
        await steam.wishlist.get_wishlist_sorted_filtered(steamid)

    assert fake_steam.requests == []


async def test_sorted_filtered_parses_items(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=SORTED)

    result = await steam.wishlist.get_wishlist_sorted_filtered(STEAMID, page_size=1)

    assert isinstance(result, WishlistSortedFiltered)
    first, second = result.items
    assert isinstance(first, WishlistSortedItem)
    assert (first.appid, first.priority, first.date_added) == (620, 1, 1689811200)
    assert first.store_item.name == "Portal 2"
    assert first.store_item.best_purchase_option.discount_pct == 80
    assert first.category_ids == []
    # Outside the requested range: no store data.
    assert (second.appid, second.priority, second.date_added) == (440, 2, 1651363200)
    assert second.store_item == StoreItem()


async def test_sorted_filtered_parses_category_ids_as_strings(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # category_ids is a repeated uint64, which Steam's JSON sends as strings.
    body = {"response": {"items": [{"appid": 620, "category_ids": ["17", "42"]}]}}
    fake_steam.api("GET", SORTED_PATH, json=body)

    result = await steam.wishlist.get_wishlist_sorted_filtered(STEAMID)

    assert result.items[0].category_ids == ["17", "42"]
    assert result.items[0].priority == 0


async def test_sorted_filtered_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SORTED_PATH, json=EMPTY)

    result = await steam.wishlist.get_wishlist_sorted_filtered(STEAMID)

    assert result == WishlistSortedFiltered(items=[])
