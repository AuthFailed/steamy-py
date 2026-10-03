r"""Tests for ``ServersAPI`` (steam.servers).

- ``get_server_list``: IGameServersService/GetServerList, GET; sends the API
  key when the client has one, else the access token.
- ``up_to_date_check``: ISteamApps/UpToDateCheck, GET; needs no credential and
  must send none.

Fixtures are real replies published by others:
servers_get_server_list.json is the GetServerList reply for a Valheim server
from michaellambgelo.github.io (_posts/2022-07-13-discord4j.md);
servers_up_to_date_check*.json are recorded UpToDateCheck replies from
fkrzski/php-steam-api-sdk (tests/Fixtures/Saloon/ISteamApps/UpToDateCheck:
out-of-date for TF2 version 1, up-to-date, and an app without version data).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    GameNotFoundError,
    InvalidAppIDError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
)
from steamy_py.models.servers import GameServer, UpToDateCheck
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

SERVER_LIST_PATH = "/IGameServersService/GetServerList/v1/"
UP_TO_DATE_PATH = "/ISteamApps/UpToDateCheck/v1/"

SERVER_LIST: dict[str, Any] = load_fixture("servers_get_server_list.json")
OUT_OF_DATE: dict[str, Any] = load_fixture("servers_up_to_date_check.json")
CURRENT: dict[str, Any] = load_fixture("servers_up_to_date_check_current.json")
UNKNOWN_APP: dict[str, Any] = load_fixture("servers_up_to_date_check_unknown_app.json")
EMPTY: dict[str, Any] = {"response": {}}

VALHEIM_FILTER = r"\appid\892970\gameaddr\173.235.136.46"


@dataclass(frozen=True)
class Endpoint:
    """One ``ServersAPI`` method, called with realistic arguments."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    path: str
    reply: dict[str, Any]
    malformed: Any  # JSON that does not fit the method's model
    operation: str  # what the error message says failed

    def serve(self, fake_steam: FakeSteam, **reply: Any) -> None:
        """Register ``reply`` (default: the realistic one) for this method."""
        fake_steam.api("GET", self.path, **(reply or {"json": self.reply}))


ENDPOINTS = [
    Endpoint(
        "get_server_list",
        lambda steam: steam.servers.get_server_list(VALHEIM_FILTER, limit=10),
        SERVER_LIST_PATH,
        SERVER_LIST,
        {"response": {"servers": [{"players": "several"}]}},
        "get server list",
    ),
    Endpoint(
        "up_to_date_check",
        lambda steam: steam.servers.up_to_date_check(440, 1),
        UP_TO_DATE_PATH,
        OUT_OF_DATE,
        {"response": {"success": True, "required_version": "latest"}},
        "check app version",
    ),
]


def endpoint_params(endpoints: list[Endpoint]) -> Any:
    return pytest.mark.parametrize(
        "endpoint", [pytest.param(endpoint, id=endpoint.name) for endpoint in endpoints]
    )


def sent(request: RecordedRequest) -> dict[str, str]:
    """The query string of ``request``, checking that no name was sent twice
    and nothing was sent as a form."""
    items = list(request.query.items())
    assert len({name for name, _ in items}) == len(items), items
    assert request.form == {}
    return dict(items)


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
async def test_call_is_one_get_to_v1(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [("GET", endpoint.path)]


@endpoint_params(ENDPOINTS)
async def test_http_500_is_raised_as_steam_api_error(
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


# -- get_server_list ----------------------------------------------------------


async def test_get_server_list_sends_filter_limit_and_only_the_api_key(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SERVER_LIST_PATH, json=SERVER_LIST)

    await steam.servers.get_server_list(VALHEIM_FILTER, limit=10)

    # The backslashes of the filter must reach Steam unchanged.
    assert sent(fake_steam.last) == {
        "filter": VALHEIM_FILTER,
        "limit": "10",
        "key": API_KEY,
    }


async def test_get_server_list_leaves_out_filter_and_limit_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SERVER_LIST_PATH, json=SERVER_LIST)

    await steam.servers.get_server_list()

    assert sent(fake_steam.last) == {"key": API_KEY}


async def test_get_server_list_sends_access_token_without_api_key(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SERVER_LIST_PATH, json=SERVER_LIST)

    await token_only_steam.servers.get_server_list(filter=r"\appid\440")

    assert sent(fake_steam.last) == {
        "filter": r"\appid\440",
        "access_token": ACCESS_TOKEN,
    }


async def test_get_server_list_without_credential_raises_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SERVER_LIST_PATH, json=SERVER_LIST)

    with pytest.raises(AuthenticationError, match="API key or access token"):
        await anonymous_steam.servers.get_server_list(r"\appid\440")

    assert fake_steam.requests == []


async def test_get_server_list_parses_real_reply(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SERVER_LIST_PATH, json=SERVER_LIST)

    (server,) = await steam.servers.get_server_list(VALHEIM_FILTER)

    assert isinstance(server, GameServer)
    assert server.model_dump() == {
        "addr": "173.235.136.46:2457",
        "gameport": 2456,
        "specport": 0,
        "steamid": "90158276832560132",
        "name": "michaellamb",
        "appid": 892970,
        "gamedir": "valheim",
        "version": "1.0.0.0",
        "product": "valheim",
        "region": -1,
        "players": 0,
        "max_players": 64,
        "bots": 0,
        "map": "michaellamb",
        "secure": False,
        "dedicated": True,
        "os": "w",
        "gametype": "0.208.1",
    }


async def test_get_server_list_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # What a filter that matches no server gives.
    fake_steam.api("GET", SERVER_LIST_PATH, json=EMPTY)

    assert await steam.servers.get_server_list(r"\appid\892970\map\none") == []


async def test_game_server_defaults_every_field() -> None:
    server = GameServer.model_validate({"addr": "198.51.100.9:27016"})

    assert server.model_dump() == {
        name: "198.51.100.9:27016" if name == "addr" else field.default
        for name, field in GameServer.model_fields.items()
    }
    assert (server.steamid, server.players, server.secure) == ("", 0, False)


@pytest.mark.parametrize("bad", [b"\\appid\\440", 440, ["\\appid\\440"]])
async def test_get_server_list_rejects_non_string_filter_before_any_request(
    steam: Steam, fake_steam: FakeSteam, bad: Any
) -> None:
    with pytest.raises(ValueError, match="filter must be a string"):
        await steam.servers.get_server_list(bad)

    assert fake_steam.requests == []


@pytest.mark.parametrize("bad", [0, -1, True, 2.5, "10", 2**32])
async def test_get_server_list_rejects_bad_limit_before_any_request(
    steam: Steam, fake_steam: FakeSteam, bad: Any
) -> None:
    with pytest.raises(ValueError, match="limit must be a positive int"):
        await steam.servers.get_server_list(r"\appid\440", limit=bad)

    assert fake_steam.requests == []


# -- up_to_date_check ---------------------------------------------------------


async def test_up_to_date_check_sends_appid_and_version_without_credential(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", UP_TO_DATE_PATH, json=OUT_OF_DATE)

    await steam.servers.up_to_date_check(440, 1)

    request = fake_steam.last
    assert sent(request) == {"appid": "440", "version": "1"}
    assert "Cookie" not in request.headers


async def test_up_to_date_check_works_without_any_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", UP_TO_DATE_PATH, json=CURRENT)

    check = await anonymous_steam.servers.up_to_date_check(440, 10828683)

    assert check.up_to_date is True
    assert sent(fake_steam.last) == {"appid": "440", "version": "10828683"}


async def test_up_to_date_check_parses_out_of_date_reply(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", UP_TO_DATE_PATH, json=OUT_OF_DATE)

    check = await steam.servers.up_to_date_check(440, 1)

    assert isinstance(check, UpToDateCheck)
    assert check.model_dump() == {
        "success": True,
        "up_to_date": False,
        "version_is_listable": False,
        "required_version": 10828683,
        "message": "Your server is out of date, please upgrade",
        "error": "",
    }


async def test_up_to_date_check_parses_current_version_reply(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", UP_TO_DATE_PATH, json=CURRENT)

    check = await steam.servers.up_to_date_check(440, 10828683)

    assert (check.success, check.up_to_date, check.version_is_listable) == (
        True,
        True,
        True,
    )
    assert check.required_version is None
    assert check.message == ""


async def test_up_to_date_check_app_without_version_data_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", UP_TO_DATE_PATH, json=UNKNOWN_APP)

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.servers.up_to_date_check(999999, 1)

    assert excinfo.value.app_id == "999999"
    assert "Couldn't get app info for the app specified." in str(excinfo.value)


async def test_up_to_date_check_failure_without_reason_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", UP_TO_DATE_PATH, json={"response": {"success": False}})

    with pytest.raises(GameNotFoundError, match="Steam gave no reason"):
        await steam.servers.up_to_date_check(999999, 1)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(EMPTY, id="empty-response"),
        pytest.param({}, id="no-response-object"),
        pytest.param({"response": []}, id="response-not-an-object"),
    ],
)
async def test_up_to_date_check_reply_without_success_raises_parsing_error(
    steam: Steam, fake_steam: FakeSteam, body: Any
) -> None:
    # Unlike service methods, UpToDateCheck always sends "success"; without it
    # the answer is unknown.
    fake_steam.api("GET", UP_TO_DATE_PATH, json=body)

    with pytest.raises(ResponseParsingError, match="Failed to check app version"):
        await steam.servers.up_to_date_check(440, 1)


@pytest.mark.parametrize("bad_id", [0, -1, True, "440", 2**32, None])
async def test_up_to_date_check_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, bad_id: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.servers.up_to_date_check(bad_id, 1)

    assert fake_steam.requests == []


@pytest.mark.parametrize("bad", [-1, True, "1", 1.0, 2**32, None])
async def test_up_to_date_check_rejects_invalid_version_before_any_request(
    steam: Steam, fake_steam: FakeSteam, bad: Any
) -> None:
    with pytest.raises(ValueError, match="Invalid version"):
        await steam.servers.up_to_date_check(440, bad)

    assert fake_steam.requests == []
