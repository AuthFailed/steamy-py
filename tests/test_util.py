"""Tests for ``UtilAPI``: ISteamWebAPIUtil/GetServerInfo and GetSupportedAPIList.

Neither method takes an input or needs a credential, and the client must not
send one even when it has them: a key would change which methods
GetSupportedAPIList lists.

``util_get_supported_api_list.json`` is a real keyless GetSupportedAPIList
reply trimmed to four of its interfaces (captured by the
aoisensi/valve-api-history bot). ``util_get_server_info.json`` has the shape
of Steam's GetServerInfo reply.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from steamy_py import ResponseParsingError, Settings, Steam, SteamAPIError
from steamy_py.models.util import (
    APIMethod,
    APIParameter,
    ServerInfo,
    SupportedAPIList,
)
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

LOGIN_COOKIE = "76561197960435530%7C%7Ctest-login-cookie"

SERVER_INFO: dict[str, Any] = load_fixture("util_get_server_info.json")
API_LIST: dict[str, Any] = load_fixture("util_get_supported_api_list.json")


@dataclass(frozen=True)
class Endpoint:
    """One ``UtilAPI`` method."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    rpc: str
    reply: dict[str, Any]

    @property
    def path(self) -> str:
        return f"/ISteamWebAPIUtil/{self.rpc}/v1/"


SERVER_INFO_ENDPOINT = Endpoint(
    "get_server_info",
    lambda steam: steam.util.get_server_info(),
    "GetServerInfo",
    SERVER_INFO,
)
API_LIST_ENDPOINT = Endpoint(
    "get_supported_api_list",
    lambda steam: steam.util.get_supported_api_list(),
    "GetSupportedAPIList",
    API_LIST,
)
ENDPOINT_PARAMS = [
    pytest.param(endpoint, id=endpoint.name)
    for endpoint in (SERVER_INFO_ENDPOINT, API_LIST_ENDPOINT)
]


def api_list_with(method: dict[str, Any]) -> dict[str, Any]:
    """A GetSupportedAPIList body listing only ``method``."""
    return {"apilist": {"interfaces": [{"name": "ISteamNews", "methods": [method]}]}}


NEWS_V2: dict[str, Any] = {
    "name": "GetNewsForApp",
    "version": 2,
    "httpmethod": "GET",
    "parameters": [{"name": "appid", "type": "uint32", "optional": False}],
}


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

    await endpoint.call(steam)

    assert len(fake_steam.requests) == 1
    assert (fake_steam.last.method, fake_steam.last.path) == ("GET", endpoint.path)


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
async def test_call_sends_no_inputs_and_no_credential(
    credentialed_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api("GET", endpoint.path, json=endpoint.reply)

    await endpoint.call(credentialed_steam)

    assert fake_steam.last.params == {}
    assert_no_credential(fake_steam.last)


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
async def test_call_works_without_any_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api("GET", endpoint.path, json=endpoint.reply)

    await endpoint.call(anonymous_steam)

    assert len(fake_steam.requests) == 1


# -- errors ------------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", ENDPOINT_PARAMS)
async def test_http_500_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api("GET", endpoint.path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError, match="HTTP 500") as excinfo:
        await endpoint.call(steam)

    assert excinfo.value.status_code == 500


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        pytest.param(SERVER_INFO_ENDPOINT, {}, id="server-info-empty"),
        pytest.param(
            SERVER_INFO_ENDPOINT, {"response": {}}, id="server-info-service-shape"
        ),
        pytest.param(
            SERVER_INFO_ENDPOINT,
            {"servertime": "soon", "servertimestring": "Sat Oct  3 07:57:07 2026"},
            id="servertime-text",
        ),
        pytest.param(
            SERVER_INFO_ENDPOINT, {"servertime": 1791039427}, id="no-servertimestring"
        ),
        pytest.param(
            SERVER_INFO_ENDPOINT,
            {"servertimestring": "Sat Oct  3 07:57:07 2026"},
            id="no-servertime",
        ),
        pytest.param(API_LIST_ENDPOINT, {}, id="api-list-empty"),
        pytest.param(API_LIST_ENDPOINT, {"response": {}}, id="api-list-service-shape"),
        pytest.param(API_LIST_ENDPOINT, {"apilist": {}}, id="no-interfaces"),
        pytest.param(
            API_LIST_ENDPOINT,
            {"apilist": {"interfaces": [{"name": "ISteamNews"}]}},
            id="interface-without-methods",
        ),
        *(
            pytest.param(
                API_LIST_ENDPOINT,
                api_list_with({k: v for k, v in NEWS_V2.items() if k != key}),
                id=f"method-without-{key}",
            )
            for key in ("name", "version", "httpmethod", "parameters")
        ),
        *(
            pytest.param(
                API_LIST_ENDPOINT,
                api_list_with(
                    {
                        **NEWS_V2,
                        "parameters": [
                            {
                                k: v
                                for k, v in NEWS_V2["parameters"][0].items()
                                if k != key
                            }
                        ],
                    }
                ),
                id=f"parameter-without-{key}",
            )
            for key in ("name", "type", "optional")
        ),
    ],
)
async def test_malformed_response_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint, body: Any
) -> None:
    fake_steam.api("GET", endpoint.path, json=body)

    operation = endpoint.name.replace("_", " ").replace("api", "API")
    with pytest.raises(ResponseParsingError, match=f"Failed to {operation}:"):
        await endpoint.call(steam)


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
        await endpoint.call(steam)


# -- GetServerInfo -------------------------------------------------------------------


async def test_get_server_info_parses_reply(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SERVER_INFO_ENDPOINT.path, json=SERVER_INFO)

    info = await steam.util.get_server_info()

    assert info == ServerInfo(
        servertime=1791039427, servertimestring="Sat Oct  3 07:57:07 2026"
    )


# -- GetSupportedAPIList ------------------------------------------------------------


async def test_get_supported_api_list_parses_interfaces(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", API_LIST_ENDPOINT.path, json=API_LIST)

    api_list = await steam.util.get_supported_api_list()

    assert isinstance(api_list, SupportedAPIList)
    assert [interface.name for interface in api_list.interfaces] == [
        "IClientStats_1046930",
        "ISteamNews",
        "ISteamWebAPIUtil",
        "IWishlistService",
    ]


async def test_get_supported_api_list_parses_method_without_descriptions(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # The base of the "method-without-..." and "parameter-without-..." cases.
    fake_steam.api("GET", API_LIST_ENDPOINT.path, json=api_list_with(NEWS_V2))

    api_list = await steam.util.get_supported_api_list()

    assert api_list.interfaces[0].methods == [
        APIMethod(
            name="GetNewsForApp",
            version=2,
            httpmethod="GET",
            parameters=[APIParameter(name="appid", type="uint32", optional=False)],
        )
    ]


async def test_get_supported_api_list_keeps_every_method_version(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", API_LIST_ENDPOINT.path, json=API_LIST)

    api_list = await steam.util.get_supported_api_list()

    methods = {
        interface.name: [(m.name, m.version, m.httpmethod) for m in interface.methods]
        for interface in api_list.interfaces
    }
    assert methods["ISteamNews"] == [
        ("GetNewsForApp", 1, "GET"),
        ("GetNewsForApp", 2, "GET"),
    ]
    assert methods["IClientStats_1046930"] == [("ReportEvent", 1, "POST")]


async def test_get_supported_api_list_parses_parameters(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", API_LIST_ENDPOINT.path, json=API_LIST)

    api_list = await steam.util.get_supported_api_list()

    util = next(i for i in api_list.interfaces if i.name == "ISteamWebAPIUtil")
    assert util.methods == [
        APIMethod(name="GetServerInfo", version=1, httpmethod="GET", parameters=[]),
        APIMethod(
            name="GetSupportedAPIList",
            version=1,
            httpmethod="GET",
            parameters=[
                APIParameter(
                    name="key", type="string", optional=True, description="access key"
                )
            ],
        ),
    ]


async def test_get_supported_api_list_leaves_missing_descriptions_none(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", API_LIST_ENDPOINT.path, json=API_LIST)

    api_list = await steam.util.get_supported_api_list()

    wishlist = next(i for i in api_list.interfaces if i.name == "IWishlistService")
    get_wishlist = next(m for m in wishlist.methods if m.name == "GetWishlist")
    assert get_wishlist.description == "Get a user's wishlist."
    assert get_wishlist.parameters == [
        APIParameter(name="steamid", type="uint64", optional=False, description=None)
    ]
    news = next(i for i in api_list.interfaces if i.name == "ISteamNews")
    assert news.methods[0].description is None


async def test_get_supported_api_list_keeps_message_and_enum_types(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", API_LIST_ENDPOINT.path, json=API_LIST)

    api_list = await steam.util.get_supported_api_list()

    wishlist = next(i for i in api_list.interfaces if i.name == "IWishlistService")
    sorted_filtered = next(
        m for m in wishlist.methods if m.name == "GetWishlistSortedFiltered"
    )
    types = {p.name: p.type for p in sorted_filtered.parameters}
    assert types["context"] == "{message}"
    assert types["sort_order"] == "{enum}"
