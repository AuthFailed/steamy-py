"""Tests for ``MarketAPI``: unofficial steamcommunity.com market and inventory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    Client,
    InvalidSteamIDError,
    MarketAPI,
    PriceInfo,
    PrivateProfileError,
    RateLimitError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
)
from steamy_py.models.market import ItemDescription, MarketHistoryEntry
from tests.conftest import make_settings
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    COMMUNITY_PREFIX,
    STEAMID,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

PRICE_PATH = "/market/priceoverview/"
PRICE_HISTORY_PATH = "/market/pricehistory/"
LOGIN_COOKIE = "76561197960435530%7C%7CeyJhbGciOiJFZERTQSJ9.cookie-value"
SEARCH_PATH = "/market/search/render/"

REDLINE = "AK-47 | Redline (Field-Tested)"
DREAMS_CASE = "Dreams & Nightmares Case"
TF2_KEY = "Mann Co. Supply Crate Key"

PRICE_REPLY: dict[str, Any] = {
    "success": True,
    "lowest_price": "$1.23",
    "volume": "1,234",
    "median_price": "$1.20",
}
# priceoverview omits volume and median_price when nothing sold in the last 24h.
NO_RECENT_SALES: dict[str, Any] = {"success": True, "lowest_price": "$0.03"}
NOT_SUCCESSFUL: dict[str, Any] = {"success": False}

# What /inventory/ answers for an account whose inventory is empty.
EMPTY_INVENTORY: dict[str, Any] = {
    "total_inventory_count": 0,
    "success": 1,
    "rwgrsn": -2,
}

# pricehistory as served to a logged-in browser (needs a steamLoginSecure cookie).
PRICE_HISTORY_REPLY: dict[str, Any] = {
    "success": True,
    "price_prefix": "$",
    "price_suffix": "",
    "prices": [
        ["Dec 06 2013 01: +0", 4.712, "47"],
        ["Oct 01 2026 01: +0", 28.874, "312"],
        ["Oct 02 2026 18: +0", 30.112, "21"],
    ],
}

STEAM_ERROR_PAGE = (
    "<!DOCTYPE html><html><head><title>Steam Community :: Error</title></head>"
    "<body><h3>Sorry!</h3><p>An error was encountered while processing your "
    "request:</p></body></html>"
)

SEARCH_DEFAULT_PARAMS = {
    "query": "",
    "start": "0",
    "count": "100",
    "sort_column": "popular",
    "sort_dir": "desc",
    "norender": "1",
}

Call = Callable[[Steam], Awaitable[object]]


def inventory_path(
    steamid: str = STEAMID, app_id: int = 730, context_id: str = "2"
) -> str:
    """Community path of an inventory (no trailing slash)."""
    return f"/inventory/{steamid}/{app_id}/{context_id}"


def listings_render_path(market_hash_name: str = REDLINE, app_id: int = 730) -> str:
    """Community path that serves an item's sell listings as JSON."""
    return f"/market/listings/{app_id}/{market_hash_name}/render/"


def raw_request(request: RecordedRequest) -> str:
    """Everything the server received for ``request``, as one string."""
    return "\n".join(
        [
            request.path,
            *(f"{name}={value}" for name, value in request.query.items()),
            *(f"{name}: {value}" for name, value in request.headers.items()),
            request.body.decode("utf-8", errors="replace"),
        ]
    )


def assert_sent_without_credentials(request: RecordedRequest) -> None:
    """``request`` is a GET to steamcommunity.com that carries no credential."""
    assert request.method == "GET"
    assert request.path.startswith(COMMUNITY_PREFIX + "/")
    assert "key" not in request.query
    assert "access_token" not in request.query
    header_names = {name.lower() for name in request.headers}
    assert "authorization" not in header_names
    assert "cookie" not in header_names
    raw = raw_request(request)
    assert API_KEY not in raw
    assert ACCESS_TOKEN not in raw
    assert LOGIN_COOKIE not in raw


# Every public method, with the route and reply Steam would serve it.
ENDPOINTS = [
    pytest.param(
        lambda steam: steam.market.get_item_price(REDLINE),
        PRICE_PATH,
        {"json": PRICE_REPLY},
        id="get_item_price",
    ),
    pytest.param(
        lambda steam: steam.market.get_market_listings(REDLINE),
        listings_render_path(),
        {"json": load_fixture("market_listings_render.json")},
        id="get_market_listings",
    ),
    pytest.param(
        lambda steam: steam.economy.get_inventory(STEAMID, 730),
        inventory_path(),
        {"json": EMPTY_INVENTORY},
        id="get_inventory",
    ),
    pytest.param(
        lambda steam: steam.market.search_market("redline", app_id=730),
        SEARCH_PATH,
        {"json": load_fixture("market_search_render.json")},
        id="search_market",
    ),
    pytest.param(
        lambda steam: steam.market.get_popular_items(app_id=730),
        SEARCH_PATH,
        {"json": load_fixture("market_search_render.json")},
        id="get_popular_items",
    ),
]

CREDENTIALS_WITHOUT_COOKIE = [
    pytest.param({"api_key": API_KEY, "access_token": ACCESS_TOKEN}, id="both"),
    pytest.param({"access_token": ACCESS_TOKEN}, id="access-token-only"),
    pytest.param({"api_key": API_KEY}, id="api-key-only"),
]

CREDENTIALS = [
    *CREDENTIALS_WITHOUT_COOKIE,
    pytest.param(
        {
            "api_key": API_KEY,
            "access_token": ACCESS_TOKEN,
            "steam_login_secure": LOGIN_COOKIE,
        },
        id="all-three",
    ),
]

INVALID_STEAMIDS = [
    pytest.param("", id="empty"),
    pytest.param("robinwalker", id="vanity-name"),
    pytest.param("STEAM_0:0:84901", id="steam2-format"),
    pytest.param("[U:1:169802]", id="steam3-format"),
    pytest.param(STEAMID[:-1], id="16-digits"),
    pytest.param(STEAMID + "0", id="18-digits"),
    pytest.param("103582791429521412", id="group-steamid"),
    pytest.param("12345678901234567", id="17-digits-not-a-steamid"),
]


# -- credentials: steamcommunity.com never receives any ------------------------


@pytest.mark.parametrize("credentials", CREDENTIALS)
@pytest.mark.parametrize(("call", "path", "reply"), ENDPOINTS)
async def test_request_goes_to_community_host_without_credentials(
    fake_steam: FakeSteam,
    settings: Settings,
    call: Call,
    path: str,
    reply: dict[str, Any],
    credentials: dict[str, str],
) -> None:
    fake_steam.community("GET", path, **reply)

    async with Steam(settings=settings, **credentials) as client:
        await call(client)

    (request,) = fake_steam.requests
    assert_sent_without_credentials(request)


@pytest.mark.parametrize(
    "credentials",
    [
        pytest.param({"access_token": ACCESS_TOKEN}, id="access-token-only"),
        pytest.param({"api_key": API_KEY}, id="api-key-only"),
    ],
)
async def test_get_item_price_works_with_a_single_credential(
    fake_steam: FakeSteam, settings: Settings, credentials: dict[str, str]
) -> None:
    fake_steam.community("GET", PRICE_PATH, json=PRICE_REPLY)

    async with Steam(settings=settings, **credentials) as client:
        price = await client.market.get_item_price(REDLINE)

    assert price == PriceInfo(
        lowest_price="$1.23", volume="1,234", median_price="$1.20"
    )
    assert_sent_without_credentials(fake_steam.last)


# -- URLs and the public surface ------------------------------------------------


def test_market_urls_derive_from_community_setting() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        STEAM_COMMUNITY_BASE_URL="https://steamcommunity.com/",
    )
    market = MarketAPI(Client(api_key=API_KEY, settings=settings))

    assert market.community_base_url == "https://steamcommunity.com"
    assert market.market_base_url == "https://steamcommunity.com/market"


def test_market_base_url_is_read_only(steam: Steam) -> None:
    with pytest.raises(AttributeError):
        steam.market.market_base_url = "https://example.com/market"  # type: ignore[misc]


async def test_trailing_slash_in_community_url_does_not_double_slashes(
    fake_steam: FakeSteam,
) -> None:
    settings = make_settings(
        fake_steam, STEAM_COMMUNITY_BASE_URL=f"{fake_steam.url}{COMMUNITY_PREFIX}/"
    )
    fake_steam.community("GET", PRICE_PATH, json=PRICE_REPLY)

    async with Steam(api_key=API_KEY, settings=settings) as client:
        await client.market.get_item_price(REDLINE)

    assert fake_steam.last.path == COMMUNITY_PREFIX + PRICE_PATH


def test_get_recent_items_was_removed(steam: Steam) -> None:
    assert not hasattr(MarketAPI, "get_recent_items")
    assert not hasattr(steam.market, "get_recent_items")


# -- get_item_price ---------------------------------------------------------------


async def test_get_item_price_sends_default_app_and_currency(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_PATH, json=PRICE_REPLY)

    await steam.market.get_item_price(REDLINE)

    assert fake_steam.last.path == COMMUNITY_PREFIX + PRICE_PATH
    assert fake_steam.last.params == {
        "appid": "730",
        "market_hash_name": REDLINE,
        "currency": "1",
    }


async def test_get_item_price_sends_given_app_and_currency(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_PATH, json=PRICE_REPLY)

    await steam.market.get_item_price(TF2_KEY, app_id=440, currency=3)

    assert fake_steam.last.params == {
        "appid": "440",
        "market_hash_name": TF2_KEY,
        "currency": "3",
    }


@pytest.mark.parametrize(
    "market_hash_name",
    [
        pytest.param(DREAMS_CASE, id="ampersand"),
        pytest.param("StatTrak™ AK-47 | Redline (Field-Tested)", id="trademark"),
        pytest.param("★ Karambit | Doppler (Factory New)", id="star"),
    ],
)
async def test_get_item_price_sends_market_hash_name_verbatim(
    steam: Steam, fake_steam: FakeSteam, market_hash_name: str
) -> None:
    fake_steam.community("GET", PRICE_PATH, json=PRICE_REPLY)

    await steam.market.get_item_price(market_hash_name)

    assert fake_steam.last.query.getall("market_hash_name") == [market_hash_name]


async def test_get_item_price_parses_price_overview(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_PATH, json=PRICE_REPLY)

    price = await steam.market.get_item_price(REDLINE)

    assert isinstance(price, PriceInfo)
    assert price.lowest_price == "$1.23"
    assert price.volume == "1,234"
    assert price.median_price == "$1.20"
    assert price.lowest_price_cents == 123
    assert price.median_price_cents == 120


async def test_get_item_price_without_recent_sales_has_no_median(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_PATH, json=NO_RECENT_SALES)

    price = await steam.market.get_item_price(REDLINE)

    assert price is not None
    assert price.lowest_price_cents == 3
    assert price.volume is None
    assert price.median_price is None
    assert price.median_price_cents is None


async def test_get_item_price_returns_none_when_not_successful(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_PATH, json=NOT_SUCCESSFUL)

    assert await steam.market.get_item_price("No Such Item") is None
    assert fake_steam.last.path == COMMUNITY_PREFIX + PRICE_PATH
    assert fake_steam.last.params["market_hash_name"] == "No Such Item"


async def test_get_item_price_keeps_price_strings_in_requested_currency(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET",
        PRICE_PATH,
        json={
            "success": True,
            "lowest_price": "1,23€",
            "volume": "1,234",
            "median_price": "1,20€",
        },
    )

    price = await steam.market.get_item_price(REDLINE, currency=3)

    assert price is not None
    assert price.lowest_price == "1,23€"
    assert price.median_price == "1,20€"


async def test_get_item_price_http_error_is_raised_with_status(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_PATH, status=502, text="Bad Gateway")

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.market.get_item_price(REDLINE)

    assert excinfo.value.status_code == 502


async def test_get_item_price_html_reply_is_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", PRICE_PATH, text=STEAM_ERROR_PAGE, content_type="text/html"
    )

    with pytest.raises(ResponseParsingError):
        await steam.market.get_item_price(REDLINE)


# -- PriceInfo / MarketHistoryEntry cents ------------------------------------------


@pytest.mark.parametrize(
    ("price", "cents"),
    [
        pytest.param("$1.23", 123, id="dollars"),
        pytest.param("$1,234.56", 123456, id="thousands-separator"),
        pytest.param("$0.29", 29, id="0.29-dollars"),
        pytest.param("$0.57", 57, id="0.57-dollars"),
        pytest.param("1,23€", 123, id="euro"),
        pytest.param("£1.23", 123, id="pound"),
        pytest.param("1.234,56€", 123456, id="euro-thousands"),
        pytest.param("1 234,56 \u0440\u0443\u0431.", 123456, id="rouble"),
        pytest.param("$1,234", 123400, id="thousands-without-decimals"),
        pytest.param("Free", None, id="no-number"),
    ],
)
@pytest.mark.parametrize("field", ["lowest_price", "median_price"])
def test_price_string_converts_to_cents(
    field: str, price: str, cents: int | None
) -> None:
    info = PriceInfo(**{field: price})

    assert getattr(info, f"{field}_cents") == cents


@pytest.mark.parametrize("field", ["lowest_price", "median_price"])
def test_missing_price_has_no_cents(field: str) -> None:
    assert getattr(PriceInfo(), f"{field}_cents") is None


def test_history_entry_price_converts_to_cents() -> None:
    entry = MarketHistoryEntry(date="Oct 02 2026 18: +0", price=0.29, volume=21)

    assert entry.price_cents == 29


# -- get_market_listings ----------------------------------------------------------


async def test_get_market_listings_passes_currency_through(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", listings_render_path(), json=load_fixture("market_listings_render.json")
    )

    await steam.market.get_market_listings(REDLINE, currency=3)

    assert fake_steam.last.query.getall("currency") == ["3"]


async def test_get_market_listings_sends_paging(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", listings_render_path(), json=load_fixture("market_listings_render.json")
    )

    await steam.market.get_market_listings(REDLINE, start=100, count=10)

    assert fake_steam.last.params["start"] == "100"
    assert fake_steam.last.params["count"] == "10"


async def test_get_market_listings_uses_render_endpoint(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", listings_render_path(), json=load_fixture("market_listings_render.json")
    )

    listings = await steam.market.get_market_listings(REDLINE)

    assert fake_steam.last.path == COMMUNITY_PREFIX + listings_render_path()
    assert listings.start == 0
    assert listings.total_count == 1517


# -- get_price_history ------------------------------------------------------------


@pytest.fixture
async def cookie_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client with every credential, including the steamLoginSecure cookie."""
    async with Steam(
        api_key=API_KEY,
        access_token=ACCESS_TOKEN,
        steam_login_secure=LOGIN_COOKIE,
        settings=settings,
    ) as client:
        yield client


async def test_get_price_history_sends_login_cookie_and_nothing_else(
    cookie_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_HISTORY_PATH, json=PRICE_HISTORY_REPLY)

    await cookie_steam.market.get_price_history(REDLINE)

    sent = fake_steam.last
    assert sent.path == COMMUNITY_PREFIX + PRICE_HISTORY_PATH
    assert sent.params == {"appid": "730", "market_hash_name": REDLINE}
    assert sent.headers["Cookie"] == f"steamLoginSecure={LOGIN_COOKIE}"
    raw = raw_request(sent)
    assert API_KEY not in raw
    assert ACCESS_TOKEN not in raw


@pytest.mark.parametrize("credentials", CREDENTIALS_WITHOUT_COOKIE)
async def test_get_price_history_without_cookie_raises_before_any_request(
    fake_steam: FakeSteam, settings: Settings, credentials: dict[str, str]
) -> None:
    fake_steam.community("GET", PRICE_HISTORY_PATH, json=PRICE_HISTORY_REPLY)

    async with Steam(settings=settings, **credentials) as client:
        with pytest.raises(AuthenticationError, match="steamLoginSecure"):
            await client.market.get_price_history(REDLINE)

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    ("status", "reply"),
    [
        pytest.param(400, {"json": []}, id="400-empty-list"),
        pytest.param(
            302,
            {"headers": {"Location": "https://steamcommunity.com/login/home/"}},
            id="redirect-to-login",
        ),
        pytest.param(403, {"text": "Forbidden"}, id="403"),
    ],
)
async def test_get_price_history_rejected_cookie_raises_authentication_error(
    cookie_steam: Steam, fake_steam: FakeSteam, status: int, reply: dict[str, Any]
) -> None:
    """Steam answers an expired or invalid cookie with ``400 []`` or a redirect
    to the login page."""
    fake_steam.community("GET", PRICE_HISTORY_PATH, status=status, **reply)

    with pytest.raises(AuthenticationError) as excinfo:
        await cookie_steam.market.get_price_history(REDLINE)

    assert excinfo.value.status_code == status
    assert LOGIN_COOKIE not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


async def test_get_price_history_server_error_is_not_an_authentication_error(
    cookie_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_HISTORY_PATH, status=500, text="Oops")

    with pytest.raises(SteamAPIError) as excinfo:
        await cookie_steam.market.get_price_history(REDLINE)

    assert type(excinfo.value) is SteamAPIError


async def test_get_price_history_parses_price_rows(
    cookie_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_HISTORY_PATH, json=PRICE_HISTORY_REPLY)

    history = await cookie_steam.market.get_price_history(REDLINE, app_id=730)

    assert history == [
        MarketHistoryEntry(date="Dec 06 2013 01: +0", price=4.712, volume=47),
        MarketHistoryEntry(date="Oct 01 2026 01: +0", price=28.874, volume=312),
        MarketHistoryEntry(date="Oct 02 2026 18: +0", price=30.112, volume=21),
    ]


async def test_get_price_history_unsuccessful_reply_returns_empty_list(
    cookie_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_HISTORY_PATH, json=NOT_SUCCESSFUL)

    assert await cookie_steam.market.get_price_history(REDLINE) == []
    assert fake_steam.last.path == COMMUNITY_PREFIX + PRICE_HISTORY_PATH


# -- get_inventory ----------------------------------------------------------------


async def test_get_inventory_sends_default_language_and_count(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", inventory_path(), json=EMPTY_INVENTORY)

    await steam.economy.get_inventory(STEAMID, 730)

    assert fake_steam.last.path == COMMUNITY_PREFIX + inventory_path()
    assert fake_steam.last.params == {"l": "english", "count": "2000"}


async def test_get_inventory_sends_context_language_count_and_start_assetid(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    path = inventory_path(app_id=753, context_id="6")
    fake_steam.community("GET", path, json=EMPTY_INVENTORY)

    await steam.economy.get_inventory(
        STEAMID,
        753,
        context_id="6",
        start_assetid="38212365110",
        count=2000,
        language="german",
    )

    assert fake_steam.last.path == COMMUNITY_PREFIX + path
    assert fake_steam.last.params == {
        "l": "german",
        "count": "2000",
        "start_assetid": "38212365110",
    }


async def test_get_inventory_parses_empty_inventory(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", inventory_path(), json=EMPTY_INVENTORY)

    inventory = await steam.economy.get_inventory(STEAMID, 730)

    assert inventory.is_success
    assert inventory.total_inventory_count == 0
    assert inventory.assets == []
    assert inventory.descriptions == []
    assert not inventory.has_more_items


async def test_get_inventory_parses_assets_and_descriptions(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", inventory_path(), json=load_fixture("market_inventory_730.json")
    )

    inventory = await steam.economy.get_inventory(STEAMID, 730)

    assert inventory.is_success
    assert inventory.total_inventory_count == 412
    assert inventory.has_more_items
    assert inventory.last_assetid == "38212365110"
    assert [item.assetid for item in inventory.assets] == [
        "38350195478",
        "38212365110",
    ]
    assert [d.market_hash_name for d in inventory.descriptions] == [
        REDLINE,
        DREAMS_CASE,
    ]


def test_item_description_parses_inventory_description() -> None:
    rifle, case = (
        ItemDescription(**description)
        for description in load_fixture("market_inventory_730.json")["descriptions"]
    )

    assert rifle.name == "AK-47 | Redline"
    assert rifle.market_hash_name == REDLINE
    assert rifle.type == "Classified Rifle"
    assert rifle.is_tradable
    assert rifle.is_marketable
    assert not rifle.is_commodity
    assert rifle.market_tradable_restriction == 7
    assert rifle.full_icon_url.endswith("/economy/image/" + rifle.icon_url)
    assert rifle.full_large_icon_url is None
    assert {tag["category"] for tag in rifle.tags} >= {"Type", "Weapon", "Exterior"}
    assert case.is_commodity


def test_item_description_accepts_nested_description_lines() -> None:
    description = load_fixture("market_inventory_730.json")["descriptions"][0]
    description["descriptions"] = [
        {"type": "html", "value": "Item set", "app_data": {"is_itemset_name": 1}}
    ]
    description["actions"] = [{"link": "steam://rungame/730", "name": "Inspect"}]

    item = ItemDescription(**description)

    assert item.descriptions[0]["app_data"] == {"is_itemset_name": 1}
    assert item.actions[0]["name"] == "Inspect"


async def test_get_market_listings_parses_listing_info(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", listings_render_path(), json=load_fixture("market_listings_render.json")
    )

    listings = await steam.market.get_market_listings(REDLINE)

    assert len(listings.listinginfo) == 1
    assert listings.has_more_results


@pytest.mark.parametrize("bad_id", INVALID_STEAMIDS)
async def test_get_inventory_rejects_invalid_steamid_before_any_request(
    steam: Steam, fake_steam: FakeSteam, bad_id: str
) -> None:
    fake_steam.community("GET", inventory_path(), json=EMPTY_INVENTORY)

    with pytest.raises(InvalidSteamIDError) as excinfo:
        await steam.economy.get_inventory(bad_id, 730)

    assert excinfo.value.steamid == bad_id
    assert fake_steam.requests == []


async def test_get_inventory_accepts_high_account_id(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    steamid = "76561200000000000"
    fake_steam.community("GET", inventory_path(steamid), json=EMPTY_INVENTORY)

    await steam.economy.get_inventory(steamid, 730)

    assert fake_steam.last.path == COMMUNITY_PREFIX + inventory_path(steamid)


async def test_get_inventory_private_inventory_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET",
        inventory_path(),
        status=403,
        text="null",
        content_type="application/json",
    )

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.economy.get_inventory(STEAMID, 730)

    assert excinfo.value.steamid == STEAMID


# -- search_market / get_popular_items --------------------------------------------


async def test_search_market_sends_default_params_without_appid(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", SEARCH_PATH, json=load_fixture("market_search_render.json")
    )

    await steam.market.search_market()

    assert fake_steam.last.path == COMMUNITY_PREFIX + SEARCH_PATH
    assert fake_steam.last.params == SEARCH_DEFAULT_PARAMS


@pytest.mark.parametrize("app_id", [730, 440])
async def test_search_market_filters_by_appid_only(
    steam: Steam, fake_steam: FakeSteam, app_id: int
) -> None:
    fake_steam.community(
        "GET", SEARCH_PATH, json=load_fixture("market_search_render.json")
    )

    await steam.market.search_market(app_id=app_id)

    assert fake_steam.last.params == {**SEARCH_DEFAULT_PARAMS, "appid": str(app_id)}
    assert not [name for name in fake_steam.last.query if name.startswith("category_")]


async def test_search_market_sends_query_paging_and_sort(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", SEARCH_PATH, json=load_fixture("market_search_render.json")
    )

    await steam.market.search_market(
        query="redline", start=100, count=10, sort_column="price", sort_dir="asc"
    )

    assert fake_steam.last.params == {
        "query": "redline",
        "start": "100",
        "count": "10",
        "sort_column": "price",
        "sort_dir": "asc",
        "norender": "1",
    }


async def test_search_market_parses_results(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", SEARCH_PATH, json=load_fixture("market_search_render.json")
    )

    results = await steam.market.search_market(app_id=730, count=2)

    assert results.success
    assert results.start == 0
    assert results.pagesize == 2
    assert results.total_count == 23214
    assert results.has_more_results
    assert results.searchdata["total_count"] == 23214
    assert [item["hash_name"] for item in results.results] == [DREAMS_CASE, REDLINE]
    assert results.results[1]["sell_price"] == 3011


async def test_search_market_rate_limited_raises_rate_limit_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", SEARCH_PATH, status=429)

    with pytest.raises(RateLimitError) as excinfo:
        await steam.market.search_market()

    assert excinfo.value.status_code == 429
    assert len(fake_steam.requests) == 1


async def test_search_market_unsuccessful_reply_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", SEARCH_PATH, json=NOT_SUCCESSFUL)

    with pytest.raises(SteamAPIError, match="Failed to search market"):
        await steam.market.search_market()


async def test_get_popular_items_searches_by_popularity(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", SEARCH_PATH, json=load_fixture("market_search_render.json")
    )

    results = await steam.market.get_popular_items(app_id=440, count=10)

    assert fake_steam.last.path == COMMUNITY_PREFIX + SEARCH_PATH
    assert fake_steam.last.params == {
        **SEARCH_DEFAULT_PARAMS,
        "count": "10",
        "appid": "440",
    }
    assert results.total_count == 23214


async def test_get_popular_items_without_app_id_searches_all_apps(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", SEARCH_PATH, json=load_fixture("market_search_render.json")
    )

    await steam.market.get_popular_items()

    assert fake_steam.last.params == SEARCH_DEFAULT_PARAMS


# -- inventory paging ----------------------------------------------------------


def second_inventory_page() -> dict[str, Any]:
    """The last page after ``market_inventory_730.json``: one new asset whose
    description repeats one from the first page."""
    first = load_fixture("market_inventory_730.json")
    asset = {**first["assets"][0], "assetid": "38212365999"}
    return {
        "assets": [asset],
        "descriptions": [first["descriptions"][0]],
        "total_inventory_count": 3,
        "success": 1,
        "rwgrsn": -2,
    }


async def test_iter_inventory_pages_follows_last_assetid(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    first = load_fixture("market_inventory_730.json")
    fake_steam.community("GET", inventory_path(), json=first)
    fake_steam.community("GET", inventory_path(), json=second_inventory_page())

    pages = [page async for page in steam.economy.iter_inventory_pages(STEAMID, 730)]

    assert len(pages) == 2
    first_request, second_request = fake_steam.requests
    assert "start_assetid" not in first_request.params
    assert second_request.params["start_assetid"] == first["last_assetid"]
    assert second_request.params["count"] == "2000"


async def test_get_full_inventory_merges_pages(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    first = load_fixture("market_inventory_730.json")
    fake_steam.community("GET", inventory_path(), json=first)
    fake_steam.community("GET", inventory_path(), json=second_inventory_page())

    inventory = await steam.economy.get_full_inventory(STEAMID, 730)

    assert [asset.assetid for asset in inventory.assets] == [
        *(asset["assetid"] for asset in first["assets"]),
        "38212365999",
    ]
    assert len(inventory.descriptions) == len(first["descriptions"])
    assert not inventory.has_more_items
    assert inventory.last_assetid is None


async def test_iter_inventory_pages_stops_when_steam_repeats_a_page(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community(
        "GET", inventory_path(), json=load_fixture("market_inventory_730.json")
    )

    with pytest.raises(SteamAPIError, match="same inventory page"):
        async for _ in steam.economy.iter_inventory_pages(STEAMID, 730):
            pass

    assert len(fake_steam.requests) == 2


# -- priceoverview for an unknown item -------------------------------------------


async def test_get_item_price_unknown_item_returns_none(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_PATH, status=500, json=NOT_SUCCESSFUL)

    assert await steam.market.get_item_price("No Such Item") is None


async def test_get_item_price_server_error_is_still_raised(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.community("GET", PRICE_PATH, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.market.get_item_price(REDLINE)

    assert excinfo.value.status_code == 500
