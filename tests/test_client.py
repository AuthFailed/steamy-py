"""Tests for the HTTP ``Client`` and the URL building in ``repos.base``."""

from __future__ import annotations

import asyncio
import contextlib
import heapq
import itertools
import logging
import sys
import traceback
from collections.abc import AsyncIterator, Awaitable, Callable
from email.utils import formatdate
from functools import partial
from http import HTTPStatus
from typing import Any
from urllib.parse import quote, quote_plus

import aiohttp
import pytest
from multidict import CIMultiDict, CIMultiDictProxy, MultiDict
from yarl import URL

import steamy_py.client as client_module
from steamy_py import (
    AuthenticationError,
    Client,
    ConfigurationError,
    NetworkError,
    RateLimitError,
    ResponseParsingError,
    ServiceUnavailableError,
    Settings,
    SteamAPIError,
    __version__,
)
from steamy_py.repos.base import BaseAPI
from tests.conftest import make_settings
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    STORE_PREFIX,
    FakeSteam,
    load_fixture,
)

# -- canned Steam replies -------------------------------------------------

SUMMARIES_PATH = "/ISteamUser/GetPlayerSummaries/v2/"
SUMMARIES = load_fixture("client_player_summaries.json")

FAMILY_PATH = "/IFamilyGroupsService/GetFamilyGroupForUser/v1/"
FAMILY = {
    "response": {
        "family_groupid": "4223817",
        "latest_time_joined": 1695326573,
        "latest_joined_family_groupid": "4223817",
        "role": 1,
    }
}

NEWS_PATH = "/ISteamNews/GetNewsForApp/v2/"
NEWS_PARAMS = {"appid": "440", "count": "1", "maxlength": "80"}
NEWS = {
    "appnews": {
        "appid": 440,
        "newsitems": [
            {
                "gid": "5762997456317419383",
                "title": "Team Fortress 2 Update Released",
                "url": "https://steamstore-a.akamaihd.net/news/externalpost/tf2_blog/5762997456317419383",
                "is_external_url": True,
                "author": "",
                "contents": "An update to Team Fortress 2 has been released...",
                "feedlabel": "TF2 Blog",
                "date": 1727395200,
                "feedname": "tf2_blog",
                "feed_type": 0,
                "appid": 440,
            }
        ],
        "count": 2310,
    }
}

STEAM_LEVEL_PATH = "/IPlayerService/GetSteamLevel/v1/"
STEAM_LEVEL = {"response": {"player_level": 42}}

APPDETAILS = {
    "570": {
        "success": True,
        "data": {"type": "game", "name": "Dota 2", "steam_appid": 570, "is_free": True},
    }
}

# A 200 page that is not JSON, as served while Steam is having trouble.
SORRY_HTML = (
    "<!DOCTYPE html><html><head><title>Sorry!</title></head><body><h1>Sorry!</h1>"
    "<p>An error was encountered while processing your request.</p></body></html>"
)

# Nothing listens on port 1, so connecting is refused straight away.
UNREACHABLE = "http://127.0.0.1:1"

# A front end that keeps redirecting to itself with the credentials still in
# the query string. aiohttp gives up with TooManyRedirects, whose own text
# holds the full first URL (credential included).
REDIRECT_LOOP: dict[str, Any] = {
    "status": 302,
    "text": "",
    "headers": {
        "Location": (
            f"{SUMMARIES_PATH}?steamids={STEAMID}"
            f"&key={API_KEY}&access_token={ACCESS_TOKEN}"
        )
    },
}


def steam_error_page(status: int) -> str:
    """The bare HTML page the Web API front end serves for an HTTP error."""
    phrase = HTTPStatus(status).phrase
    detail = ""
    if status in (401, 403):
        detail = (
            "Access is denied. Retrying will not help. "
            "Please verify your <pre>key=</pre> parameter."
        )
    return (
        f"<html><head><title>{phrase}</title></head>"
        f"<body><h1>{phrase}</h1>{detail}</body></html>"
    )


def error_reply(status: int) -> dict[str, Any]:
    """``fake_steam.api`` kwargs for an HTTP error with Steam's HTML body."""
    return {
        "status": status,
        "text": steam_error_page(status),
        "content_type": "text/html",
    }


# -- helpers --------------------------------------------------------------

SECRETS = {"API_KEY": API_KEY, "ACCESS_TOKEN": ACCESS_TOKEN}


def leaked_secrets(text: str) -> list[str]:
    """Names of the test credentials that appear in ``text``."""
    return [name for name, secret in SECRETS.items() if secret in text]


def format_exception(exc: BaseException) -> str:
    """The full traceback as ``logging``/``traceback`` would print it."""
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def offline_settings(**overrides: Any) -> Settings:
    """Settings for tests that never touch the network."""
    values: dict[str, Any] = {
        "STEAM_API_BASE_URL": "https://api.steampowered.com",
        "STEAM_STORE_BASE_URL": "https://store.steampowered.com/api",
        "RATE_LIMIT_ENABLED": False,
        "MAX_RETRIES": 0,
        "RETRY_DELAY": 0.0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@contextlib.asynccontextmanager
async def silent_server() -> AsyncIterator[str]:
    """A TCP server that accepts connections and never answers."""

    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            await reader.read()
        finally:
            writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.close()
        await server.wait_closed()


class VirtualTime:
    """Deterministic stand-in for the client's ``time`` and ``asyncio.sleep``.

    Sleeps are recorded and advance the virtual clock instantly. Inside
    :meth:`run_concurrently` a sleep instead parks its task until the clock
    reaches its wake-up time, so concurrent sleepers wake in time order.
    """

    def __init__(self) -> None:
        self.now = 1_000.0
        self.sleeps: list[float] = []
        self._parked: list[tuple[float, int, asyncio.Future[None]]] = []
        self._order = itertools.count()
        self._concurrent = False

    def time(self) -> float:
        return self.now

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        if not self._concurrent:
            self.now += max(delay, 0.0)
            return
        future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        wake_at = self.now + max(delay, 0.0)
        heapq.heappush(self._parked, (wake_at, next(self._order), future))
        await future

    async def run_concurrently(self, *coros: Awaitable[Any]) -> list[Any]:
        """Run ``coros`` together, waking one parked sleeper at a time."""
        self._concurrent = True
        gathered = asyncio.gather(*coros)
        try:
            for _ in range(1_000):
                for _ in range(20):  # let every runnable task reach its next wait
                    await asyncio.sleep(0)
                if gathered.done() or not self._parked:
                    break
                wake_at, _, future = heapq.heappop(self._parked)
                self.now = max(self.now, wake_at)
                future.set_result(None)
            return await asyncio.wait_for(gathered, timeout=5)
        finally:
            self._concurrent = False


class _AsyncioWithSleep:
    """``asyncio`` as the client module sees it, with ``sleep`` replaced."""

    def __init__(self, sleep: Callable[[float], Awaitable[None]]) -> None:
        self.sleep = sleep

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)


ClientFactory = Callable[..., Client]


@pytest.fixture
async def make_client(fake_steam: FakeSteam) -> AsyncIterator[ClientFactory]:
    """Build clients for ``fake_steam`` (settings overridable); closes them all."""
    clients: list[Client] = []

    def factory(
        *,
        api_key: str | None = API_KEY,
        access_token: str | None = ACCESS_TOKEN,
        **overrides: Any,
    ) -> Client:
        client = Client(
            api_key=api_key,
            access_token=access_token,
            settings=make_settings(fake_steam, **overrides),
        )
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.close()


@pytest.fixture
def client(make_client: ClientFactory) -> Client:
    """A client with both credentials, no retries and no rate limiting."""
    return make_client()


@pytest.fixture
def virtual_time(monkeypatch: pytest.MonkeyPatch) -> VirtualTime:
    """Make the client's clock and sleeps virtual (no real waiting)."""
    clock = VirtualTime()
    monkeypatch.setattr(client_module, "time", clock)
    monkeypatch.setattr(client_module, "asyncio", _AsyncioWithSleep(clock.sleep))
    return clock


def url_for(fake_steam: FakeSteam, path: str) -> str:
    return fake_steam.url + path


async def get_summaries(client: Client, fake_steam: FakeSteam) -> dict[str, Any]:
    """GET ISteamUser/GetPlayerSummaries/v2 with the API key."""
    return await client.request(
        "GET", url_for(fake_steam, SUMMARIES_PATH), params={"steamids": STEAMID}
    )


# -- credentials ----------------------------------------------------------


@pytest.mark.parametrize(
    ("auth_type", "path", "params", "reply", "credential"),
    [
        pytest.param(
            "api_key",
            SUMMARIES_PATH,
            {"steamids": STEAMID},
            SUMMARIES,
            {"key": API_KEY},
            id="api_key",
        ),
        pytest.param(
            "access_token",
            FAMILY_PATH,
            {"steamid": STEAMID},
            FAMILY,
            {"access_token": ACCESS_TOKEN},
            id="access_token",
        ),
        pytest.param("none", NEWS_PATH, NEWS_PARAMS, NEWS, {}, id="none"),
    ],
)
async def test_request_sends_only_the_credential_for_auth_type(
    client: Client,
    fake_steam: FakeSteam,
    auth_type: str,
    path: str,
    params: dict[str, str],
    reply: dict[str, Any],
    credential: dict[str, str],
) -> None:
    fake_steam.api("GET", path, json=reply)

    data = await client.request(
        "GET", url_for(fake_steam, path), params=params, auth_type=auth_type
    )

    assert data == reply
    sent = fake_steam.last
    assert (sent.method, sent.path) == ("GET", path)
    assert sorted(sent.query.items()) == sorted({**params, **credential}.items())


async def test_request_defaults_to_api_key_auth(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)

    await get_summaries(client, fake_steam)

    assert fake_steam.last.params == {"steamids": STEAMID, "key": API_KEY}


@pytest.mark.parametrize(
    ("auth_type", "credentials", "message"),
    [
        pytest.param(
            "api_key",
            {"access_token": ACCESS_TOKEN},
            "API key is required",
            id="no-api-key",
        ),
        pytest.param(
            "access_token",
            {"api_key": API_KEY},
            "Access token is required",
            id="no-access-token",
        ),
        pytest.param(
            "api_key",
            {"api_key": "", "access_token": ACCESS_TOKEN},
            "API key is required",
            id="empty-api-key",
        ),
        pytest.param(
            "access_token",
            {"api_key": API_KEY, "access_token": ""},
            "Access token is required",
            id="empty-access-token",
        ),
    ],
)
async def test_missing_credential_raises_authentication_error_before_sending(
    make_client: ClientFactory,
    fake_steam: FakeSteam,
    auth_type: str,
    credentials: dict[str, str],
    message: str,
) -> None:
    client = make_client(**{"api_key": None, "access_token": None, **credentials})

    with pytest.raises(AuthenticationError, match=message) as excinfo:
        await client.request(
            "GET", url_for(fake_steam, FAMILY_PATH), auth_type=auth_type
        )

    assert excinfo.value.status_code is None

    assert fake_steam.requests == []


@pytest.mark.parametrize("auth_type", ["bearer", "API_KEY", ""])
async def test_invalid_auth_type_raises_value_error_before_sending(
    client: Client, fake_steam: FakeSteam, auth_type: str
) -> None:
    with pytest.raises(ValueError, match="Invalid auth_type"):
        await client.request(
            "GET", url_for(fake_steam, SUMMARIES_PATH), auth_type=auth_type
        )

    assert fake_steam.requests == []


async def test_request_does_not_mutate_caller_params(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    params = {"steamids": STEAMID}

    await client.request("GET", url_for(fake_steam, SUMMARIES_PATH), params=params)

    assert params == {"steamids": STEAMID}
    assert fake_steam.last.params == {"steamids": STEAMID, "key": API_KEY}


@pytest.mark.parametrize("auth_type", ["none", "api_key"])
@pytest.mark.parametrize(
    "params",
    [
        pytest.param([("tag", "a"), ("tag", "b"), ("x", "1")], id="pairs"),
        pytest.param(
            MultiDict([("tag", "a"), ("tag", "b"), ("x", "1")]), id="multidict"
        ),
    ],
)
async def test_request_keeps_repeated_query_keys(
    client: Client, fake_steam: FakeSteam, params: Any, auth_type: str
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS)

    await client.request(
        "GET", url_for(fake_steam, NEWS_PATH), params=params, auth_type=auth_type
    )

    expected = [("tag", "a"), ("tag", "b"), ("x", "1")]
    if auth_type == "api_key":
        expected.append(("key", API_KEY))
    assert list(fake_steam.last.query.items()) == expected


async def test_credential_replaces_a_caller_supplied_credential_param(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)

    await client.request(
        "GET",
        url_for(fake_steam, SUMMARIES_PATH),
        params={"key": "other", "steamids": STEAMID},
    )

    assert list(fake_steam.last.query.items()) == [
        ("steamids", STEAMID),
        ("key", API_KEY),
    ]


@pytest.mark.parametrize("params", ["steamids=1", b"steamids=1"])
async def test_string_params_are_rejected_before_sending(
    client: Client, fake_steam: FakeSteam, params: Any
) -> None:
    with pytest.raises(TypeError):
        await client.request(
            "GET", url_for(fake_steam, NEWS_PATH), params=params, auth_type="none"
        )

    assert fake_steam.requests == []


async def test_reused_params_do_not_carry_credentials_between_requests(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FAMILY_PATH, json=FAMILY)
    params = {"steamid": STEAMID}

    for auth_type in ("api_key", "access_token", "none"):
        await client.request(
            "GET", url_for(fake_steam, FAMILY_PATH), params=params, auth_type=auth_type
        )

    assert [r.params for r in fake_steam.requests] == [
        {"steamid": STEAMID, "key": API_KEY},
        {"steamid": STEAMID, "access_token": ACCESS_TOKEN},
        {"steamid": STEAMID},
    ]


# -- headers --------------------------------------------------------------


async def test_sends_library_user_agent(client: Client, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS)

    await client.request(
        "GET", url_for(fake_steam, NEWS_PATH), params=NEWS_PARAMS, auth_type="none"
    )

    assert fake_steam.last.headers["User-Agent"] == f"steamy-py/{__version__}"


async def test_asks_for_json(client: Client, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS)

    await client.request(
        "GET", url_for(fake_steam, NEWS_PATH), params=NEWS_PARAMS, auth_type="none"
    )

    assert fake_steam.last.headers["Accept"] == "application/json"


# -- HTTP errors and retries ----------------------------------------------


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_server_error_is_retried_until_success(
    make_client: ClientFactory, fake_steam: FakeSteam, status: int
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(status))
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    client = make_client(MAX_RETRIES=1)

    data = await get_summaries(client, fake_steam)

    assert data == SUMMARIES
    assert len(fake_steam.requests_to(SUMMARIES_PATH)) == 2


async def test_retry_resends_the_same_query(
    make_client: ClientFactory, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(503))
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    client = make_client(MAX_RETRIES=1)

    await get_summaries(client, fake_steam)

    first, second = fake_steam.requests
    assert first.params == second.params == {"steamids": STEAMID, "key": API_KEY}


async def test_succeeds_on_the_last_allowed_attempt(
    make_client: ClientFactory, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(500))
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(502))
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    client = make_client(MAX_RETRIES=2)

    assert await get_summaries(client, fake_steam) == SUMMARIES
    assert len(fake_steam.requests) == 3


@pytest.mark.parametrize(
    "max_retries",
    [
        pytest.param(0, id="no-retries"),
        pytest.param(1, id="1"),
        pytest.param(3, id="3"),
    ],
)
async def test_gives_up_after_max_retries(
    make_client: ClientFactory, fake_steam: FakeSteam, max_retries: int
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(500))
    client = make_client(MAX_RETRIES=max_retries)

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.status_code == 500
    assert len(fake_steam.requests) == max_retries + 1


async def test_retry_delay_doubles_after_each_failed_attempt(
    make_client: ClientFactory, fake_steam: FakeSteam, virtual_time: VirtualTime
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(502))
    client = make_client(MAX_RETRIES=3, RETRY_DELAY=1.5)

    with pytest.raises(SteamAPIError):
        await get_summaries(client, fake_steam)

    assert virtual_time.sleeps == [1.5, 3.0, 6.0]


@pytest.mark.parametrize("status", [400, 401, 403, 404, 500, 503])
async def test_http_error_raises_steam_api_error_with_status_code(
    client: Client, fake_steam: FakeSteam, status: int
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(status))

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.status_code == status


async def test_http_error_message_names_status_and_endpoint(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(403))

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    message = str(excinfo.value)
    assert "HTTP 403 Forbidden" in message
    assert f"{fake_steam.url}{SUMMARIES_PATH}" in message
    assert "steamids" not in message


@pytest.mark.parametrize("status", [400, 401, 403, 404])
async def test_client_error_is_not_retried(
    make_client: ClientFactory, fake_steam: FakeSteam, status: int
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(status))
    client = make_client(MAX_RETRIES=2)

    with pytest.raises(SteamAPIError):
        await get_summaries(client, fake_steam)

    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    ("status", "error"),
    [(401, AuthenticationError), (503, ServiceUnavailableError)],
)
async def test_http_status_maps_to_specific_exception(
    client: Client, fake_steam: FakeSteam, status: int, error: type[SteamAPIError]
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(status))

    with pytest.raises(error) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.status_code == status


async def test_redirect_loop_is_not_reported_as_http_status_zero(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **REDIRECT_LOOP)

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.status_code != 0
    assert "HTTP 0 " not in str(excinfo.value)


# -- x-eresult --------------------------------------------------------------


async def test_x_eresult_ok_returns_body(client: Client, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", FAMILY_PATH, json=FAMILY, headers={"x-eresult": "1"})

    data = await client.request(
        "GET",
        url_for(fake_steam, FAMILY_PATH),
        params={"steamid": STEAMID},
        auth_type="access_token",
    )

    assert data == FAMILY


async def test_x_eresult_failure_raises_steam_api_error(
    client: Client, fake_steam: FakeSteam
) -> None:
    # EResult 15 = AccessDenied; Steam still answers 200 with an empty response.
    fake_steam.api(
        "GET", FAMILY_PATH, json={"response": {}}, headers={"x-eresult": "15"}
    )

    with pytest.raises(SteamAPIError):
        await client.request(
            "GET",
            url_for(fake_steam, FAMILY_PATH),
            params={"steamid": STEAMID},
            auth_type="access_token",
        )


# -- HTTP 429 -------------------------------------------------------------


async def test_rate_limited_request_is_retried_after_retry_after(
    make_client: ClientFactory, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, status=429, headers={"Retry-After": "0"})
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    client = make_client(MAX_RETRIES=1)

    assert await get_summaries(client, fake_steam) == SUMMARIES
    assert len(fake_steam.requests) == 2


async def test_rate_limit_waits_for_retry_after_seconds(
    make_client: ClientFactory, fake_steam: FakeSteam, virtual_time: VirtualTime
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, status=429, headers={"Retry-After": "7"})
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    client = make_client(MAX_RETRIES=1, RETRY_DELAY=1.0)

    await get_summaries(client, fake_steam)

    assert virtual_time.sleeps == [7.0]


async def test_rate_limit_without_retry_after_waits_retry_delay(
    make_client: ClientFactory, fake_steam: FakeSteam, virtual_time: VirtualTime
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, status=429)
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    client = make_client(MAX_RETRIES=1, RETRY_DELAY=2.5)

    await get_summaries(client, fake_steam)

    assert virtual_time.sleeps == [2.5]


async def test_rate_limited_on_every_attempt_raises_rate_limit_error(
    make_client: ClientFactory, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, status=429, headers={"Retry-After": "0"})
    client = make_client(MAX_RETRIES=2)

    with pytest.raises(RateLimitError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.status_code == 429
    assert len(fake_steam.requests) == 3


@pytest.mark.parametrize(
    "statuses",
    [
        pytest.param([500, 429], id="500-then-429"),
        pytest.param([429, 500, 429], id="429-500-429"),
    ],
)
async def test_mixed_failures_raise_the_last_non_rate_limit_error(
    make_client: ClientFactory, fake_steam: FakeSteam, statuses: list[int]
) -> None:
    for status in statuses:
        headers = {"Retry-After": "0"} if status == 429 else {}
        fake_steam.api("GET", SUMMARIES_PATH, status=status, headers=headers)
    client = make_client(MAX_RETRIES=len(statuses) - 1)

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    assert not isinstance(excinfo.value, RateLimitError)
    assert excinfo.value.status_code == 500
    assert len(fake_steam.requests) == len(statuses)


async def test_rate_limit_does_not_sleep_when_no_retry_is_left(
    client: Client, fake_steam: FakeSteam, virtual_time: VirtualTime
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, status=429, headers={"Retry-After": "3600"})

    with pytest.raises(RateLimitError):
        await get_summaries(client, fake_steam)

    assert virtual_time.sleeps == []


async def test_rate_limit_error_carries_retry_after(
    client: Client, fake_steam: FakeSteam, virtual_time: VirtualTime
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, status=429, headers={"Retry-After": "30"})

    with pytest.raises(RateLimitError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.retry_after == 30


@pytest.mark.parametrize(
    ("offset", "expected_wait"),
    [pytest.param(7, 7.0, id="future"), pytest.param(-30, 0.0, id="past")],
)
async def test_http_date_retry_after_is_honoured(
    make_client: ClientFactory,
    fake_steam: FakeSteam,
    virtual_time: VirtualTime,
    offset: int,
    expected_wait: float,
) -> None:
    virtual_time.now = 1_700_000_000.0
    retry_at = formatdate(virtual_time.now + offset, usegmt=True)
    fake_steam.api("GET", SUMMARIES_PATH, status=429, headers={"Retry-After": retry_at})
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    client = make_client(MAX_RETRIES=1)

    assert await get_summaries(client, fake_steam) == SUMMARIES
    assert len(fake_steam.requests) == 2
    assert virtual_time.sleeps == [pytest.approx(expected_wait)]


# -- bad bodies and network failures ----------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param({"text": SORRY_HTML, "content_type": "text/html"}, id="html"),
        pytest.param(
            {"text": '{"response": {"players": [', "content_type": "application/json"},
            id="truncated-json",
        ),
        pytest.param({}, id="empty-body"),
    ],
)
async def test_invalid_json_raises_response_parsing_error(
    client: Client, fake_steam: FakeSteam, reply: dict[str, Any]
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **reply)

    with pytest.raises(ResponseParsingError, match="Invalid JSON response"):
        await get_summaries(client, fake_steam)


async def test_connection_refused_raises_network_error(
    make_client: ClientFactory,
) -> None:
    api = BaseAPI(make_client(STEAM_API_BASE_URL=UNREACHABLE))

    with pytest.raises(NetworkError) as excinfo:
        await api._request(
            "ISteamUser", "GetPlayerSummaries", "v2", params={"steamids": STEAMID}
        )

    assert excinfo.value.status_code is None
    assert "127.0.0.1:1" in str(excinfo.value)


async def test_timeout_raises_network_error(client: Client) -> None:
    async with silent_server() as base_url:
        with pytest.raises(NetworkError):
            await client.request(
                "GET",
                base_url + SUMMARIES_PATH,
                params={"steamids": STEAMID},
                timeout=aiohttp.ClientTimeout(total=0.05),
            )


# -- session lifecycle ------------------------------------------------------


async def test_context_manager_opens_and_closes_session(settings: Settings) -> None:
    client = Client(api_key=API_KEY, settings=settings)

    async with client as entered:
        session = client._session
        assert entered is client
        assert session is not None
        assert not session.closed

    assert session.closed


async def test_request_connects_on_first_use(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS)
    assert client._session is None

    data = await client.request(
        "GET", url_for(fake_steam, NEWS_PATH), params=NEWS_PARAMS, auth_type="none"
    )

    assert data == NEWS
    assert client._session is not None
    assert not client._session.closed


async def test_connect_reuses_open_session(client: Client) -> None:
    await client.connect()
    session = client._session

    await client.connect()

    assert client._session is session


async def test_connect_after_close_opens_a_new_session(client: Client) -> None:
    await client.connect()
    first = client._session
    await client.close()

    await client.connect()

    assert client._session is not first
    assert client._session is not None
    assert not client._session.closed


async def test_close_without_connect_is_a_no_op() -> None:
    client = Client(api_key=API_KEY, settings=offline_settings())

    await client.close()

    assert client._session is None


async def test_request_after_close_reconnects(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS)
    url = url_for(fake_steam, NEWS_PATH)
    await client.request("GET", url, params=NEWS_PARAMS, auth_type="none")
    await client.close()

    data = await client.request("GET", url, params=NEWS_PARAMS, auth_type="none")

    assert data == NEWS


# -- client-side rate limiting ----------------------------------------------


async def test_rate_limiter_disabled_never_waits(
    client: Client, fake_steam: FakeSteam, virtual_time: VirtualTime
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS)

    for _ in range(3):
        await client.request(
            "GET", url_for(fake_steam, NEWS_PATH), params=NEWS_PARAMS, auth_type="none"
        )

    assert virtual_time.sleeps == []


async def test_rate_limiter_waits_out_the_rest_of_the_interval(
    make_client: ClientFactory, fake_steam: FakeSteam, virtual_time: VirtualTime
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS)
    client = make_client(RATE_LIMIT_ENABLED=True, REQUESTS_PER_SECOND=4.0)
    url = url_for(fake_steam, NEWS_PATH)

    await client.request("GET", url, params=NEWS_PARAMS, auth_type="none")
    virtual_time.now += 0.1
    await client.request("GET", url, params=NEWS_PARAMS, auth_type="none")
    virtual_time.now += 1.0
    await client.request("GET", url, params=NEWS_PARAMS, auth_type="none")

    assert virtual_time.sleeps == [pytest.approx(0.15)]


async def test_rate_limiter_spaces_out_concurrent_requests(
    monkeypatch: pytest.MonkeyPatch, virtual_time: VirtualTime
) -> None:
    client = Client(
        settings=offline_settings(RATE_LIMIT_ENABLED=True, REQUESTS_PER_SECOND=4.0)
    )
    sent_at: list[float] = []

    async def send(*args: Any, **kwargs: Any) -> dict[str, Any]:
        sent_at.append(virtual_time.now)
        return NEWS

    monkeypatch.setattr(client, "_send", send)
    url = "https://api.steampowered.com" + NEWS_PATH
    try:
        await virtual_time.run_concurrently(
            *(client.request("GET", url, auth_type="none") for _ in range(3))
        )
    finally:
        await client.close()

    gaps = [later - earlier for earlier, later in itertools.pairwise(sorted(sent_at))]
    assert len(sent_at) == 3
    assert min(gaps) >= 0.25 - 1e-9, sent_at


# -- logging configuration --------------------------------------------------


def test_creating_client_leaves_root_logger_alone() -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    root.handlers.clear()
    try:
        Client(api_key=API_KEY, settings=offline_settings())
        added = root.handlers[:]
    finally:
        for handler in root.handlers:
            handler.close()
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)

    assert added == []


# -- credentials never leak (#17) -------------------------------------------

# Failures where Steam answered. Values: replies, expected error, settings.
ANSWERED_FAILURES = [
    pytest.param([error_reply(401)], SteamAPIError, {}, id="http-401"),
    pytest.param([error_reply(403)], SteamAPIError, {}, id="http-403"),
    pytest.param([error_reply(500)], SteamAPIError, {}, id="http-500"),
    pytest.param(
        [{"status": 429, "headers": {"Retry-After": "0"}}],
        RateLimitError,
        {},
        id="rate-limit-exhausted",
    ),
    pytest.param(
        [{"text": SORRY_HTML, "content_type": "text/html"}],
        ResponseParsingError,
        {},
        id="invalid-json",
    ),
    pytest.param([REDIRECT_LOOP], SteamAPIError, {}, id="redirect-loop"),
]
CONNECTION_REFUSED = ([], NetworkError, {"STEAM_API_BASE_URL": UNREACHABLE})
FAILURES = [
    *ANSWERED_FAILURES,
    pytest.param(*CONNECTION_REFUSED, id="connection-refused"),
]

CREDENTIAL_PARAM = {
    "api_key": ("key", API_KEY),
    "access_token": ("access_token", ACCESS_TOKEN),
}


async def fail_summaries_request(
    make_client: ClientFactory,
    fake_steam: FakeSteam,
    replies: list[dict[str, Any]],
    error: type[SteamAPIError],
    overrides: dict[str, Any],
    auth_type: str = "api_key",
) -> SteamAPIError:
    """Make GetPlayerSummaries fail as described and return the raised error."""
    for reply in replies:
        fake_steam.api("GET", SUMMARIES_PATH, **reply)
    api = BaseAPI(make_client(MAX_RETRIES=1, **overrides))

    with pytest.raises(error) as excinfo:
        await api._request(
            "ISteamUser",
            "GetPlayerSummaries",
            "v2",
            params={"steamids": STEAMID},
            auth_type=auth_type,
        )
    return excinfo.value


@pytest.mark.parametrize("auth_type", ["api_key", "access_token"])
@pytest.mark.parametrize(("replies", "error", "overrides"), FAILURES)
async def test_failure_never_exposes_credentials(
    make_client: ClientFactory,
    fake_steam: FakeSteam,
    caplog: pytest.LogCaptureFixture,
    replies: list[dict[str, Any]],
    error: type[SteamAPIError],
    overrides: dict[str, Any],
    auth_type: str,
) -> None:
    caplog.set_level(logging.DEBUG, logger="steamy_py")

    exc = await fail_summaries_request(
        make_client, fake_steam, replies, error, overrides, auth_type
    )

    exposed = {
        "str": str(exc),
        "repr": repr(exc),
        "attributes": repr(vars(exc)),
        "traceback": format_exception(exc),
        "logs": caplog.text,
    }
    assert {where: leaked_secrets(text) for where, text in exposed.items()} == {
        where: [] for where in exposed
    }
    # The credential really was on the wire, and the failure really was logged.
    name, secret = CREDENTIAL_PARAM[auth_type]
    if error is not NetworkError:
        assert fake_steam.requests
    assert all(sent.params[name] == secret for sent in fake_steam.requests)
    assert any(r.name.startswith("steamy_py") for r in caplog.records)


@pytest.mark.parametrize(("replies", "error", "overrides"), FAILURES)
async def test_failure_is_not_chained_to_the_aiohttp_error(
    make_client: ClientFactory,
    fake_steam: FakeSteam,
    replies: list[dict[str, Any]],
    error: type[SteamAPIError],
    overrides: dict[str, Any],
) -> None:
    exc = await fail_summaries_request(
        make_client, fake_steam, replies, error, overrides
    )

    assert exc.__cause__ is None
    assert exc.__context__ is None


def test_raise_unchained_drops_the_exception_being_handled() -> None:
    error = NetworkError("sanitized")

    with pytest.raises(NetworkError) as excinfo:
        try:
            raise ConnectionRefusedError(111, "Connection refused")
        except ConnectionRefusedError:
            client_module._raise_unchained(error)

    assert excinfo.value is error
    assert error.__context__ is None
    assert error.__cause__ is None


@pytest.mark.skipif(
    sys.version_info >= (3, 14) or not hasattr(asyncio.tasks, "_PyTask"),
    reason="from 3.14 aiohttp cannot run inside asyncio.tasks._PyTask",
)
async def test_network_error_is_not_chained_under_pure_python_task(
    make_client: ClientFactory,
) -> None:
    api = BaseAPI(make_client(STEAM_API_BASE_URL=UNREACHABLE))
    request = api._request(
        "ISteamUser", "GetPlayerSummaries", "v2", params={"steamids": STEAMID}
    )
    loop = asyncio.get_running_loop()
    task = asyncio.tasks._PyTask(request, loop=loop)  # type: ignore[attr-defined]

    with pytest.raises(NetworkError) as excinfo:
        await task

    assert excinfo.value.__context__ is None


async def test_successful_request_logs_do_not_contain_credentials(
    client: Client, fake_steam: FakeSteam, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="steamy_py")
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)
    fake_steam.api("GET", FAMILY_PATH, json=FAMILY)
    api = BaseAPI(client)

    await api._request(
        "ISteamUser", "GetPlayerSummaries", "v2", params={"steamids": STEAMID}
    )
    await api._request(
        "IFamilyGroupsService",
        "GetFamilyGroupForUser",
        params={"steamid": STEAMID},
        auth_type="access_token",
    )

    assert "Successful response from" in caplog.text
    assert leaked_secrets(caplog.text) == []


# -- Client._redact / Client._describe_error ----------------------------------

# Characters that change under URL encoding, to tell the encoded forms apart.
AWKWARD_SECRET = "Zm9v YmFy/+=="


def test_redact_masks_configured_credentials_anywhere_in_text() -> None:
    client = Client(
        api_key=API_KEY, access_token=ACCESS_TOKEN, settings=offline_settings()
    )

    text = f"proxy said: token {ACCESS_TOKEN} rejected, key {API_KEY} unknown"

    assert client._redact(text) == "proxy said: token *** rejected, key *** unknown"


@pytest.mark.parametrize("credential", ["api_key", "access_token"])
@pytest.mark.parametrize(
    "encode",
    [
        pytest.param(str, id="literal"),
        pytest.param(partial(quote, safe=""), id="percent-encoded"),
        pytest.param(quote_plus, id="form-encoded"),
        pytest.param(
            lambda secret: URL("http://h/").with_query(key=secret).raw_query_string[4:],
            id="yarl-encoded",
        ),
    ],
)
def test_redact_masks_url_encoded_credentials(
    credential: str, encode: Callable[[str], str]
) -> None:
    client = Client(settings=offline_settings(), **{credential: AWKWARD_SECRET})

    assert client._redact(f"upstream: {encode(AWKWARD_SECRET)}.") == "upstream: ***."


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        pytest.param(
            "GET https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
            "?key=0123456789ABCDEF0123456789ABCDEF&steamids=76561197960435530",
            "GET https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
            "?key=***&steamids=76561197960435530",
            id="key",
        ),
        pytest.param(
            "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
            "?steamid=76561197960435530&access_token=eyJhbGciOi.eyJpc3Mi.c2ln#top",
            "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
            "?steamid=76561197960435530&access_token=***#top",
            id="access_token",
        ),
        pytest.param(
            "url='https://api.steampowered.com/x/?KEY=abc' failed",
            "url='https://api.steampowered.com/x/?KEY=***' failed",
            id="upper-case-in-quotes",
        ),
        pytest.param(
            "form: key=abc access_token=def",
            "form: key=*** access_token=***",
            id="space-separated",
        ),
    ],
)
def test_redact_masks_unknown_credential_query_values(text: str, expected: str) -> None:
    client = Client(settings=offline_settings())  # no credentials configured

    assert client._redact(text) == expected


def test_redact_leaves_other_parameters_alone() -> None:
    client = Client(api_key=API_KEY, settings=offline_settings())
    text = "?steamid=76561197960435530&appid=440&monkey=banana&format=json"

    assert client._redact(text) == text


def test_describe_error_drops_query_string_from_http_errors() -> None:
    client = Client(
        api_key=API_KEY, access_token=ACCESS_TOKEN, settings=offline_settings()
    )
    url = URL("https://api.steampowered.com" + SUMMARIES_PATH).with_query(
        key=API_KEY, steamids=STEAMID
    )
    info = aiohttp.RequestInfo(url, "GET", CIMultiDictProxy(CIMultiDict()), url)
    error = aiohttp.ClientResponseError(info, (), status=403, message="Forbidden")
    assert API_KEY in str(error)  # aiohttp's own text carries the full URL

    assert client._describe_error(error) == (
        "HTTP 403 Forbidden for https://api.steampowered.com" + SUMMARIES_PATH
    )


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        pytest.param(
            aiohttp.InvalidURL(
                "https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
                f"?access_token={ACCESS_TOKEN}&steamid={STEAMID}"
            ),
            "InvalidURL: https://api.steampowered.com/IPlayerService/GetOwnedGames/v1/"
            f"?access_token=***&steamid={STEAMID}",
            id="url-in-message",
        ),
        pytest.param(
            aiohttp.ClientConnectionError(f"proxy rejected {API_KEY}"),
            "ClientConnectionError: proxy rejected ***",
            id="secret-in-message",
        ),
    ],
)
def test_describe_error_redacts_other_errors(
    error: aiohttp.ClientError, expected: str
) -> None:
    client = Client(
        api_key=API_KEY, access_token=ACCESS_TOKEN, settings=offline_settings()
    )

    assert client._describe_error(error) == expected


# -- repos.base URL building ------------------------------------------------


@pytest.mark.parametrize(
    "base_url", ["https://api.steampowered.com", "https://api.steampowered.com/"]
)
def test_build_url_joins_interface_method_and_version(base_url: str) -> None:
    api = BaseAPI(Client(settings=offline_settings(STEAM_API_BASE_URL=base_url)))

    assert (
        api._build_url("ISteamUser", "GetPlayerSummaries", "v2")
        == "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
    )


def test_build_url_defaults_to_version_1() -> None:
    api = BaseAPI(Client(settings=offline_settings()))

    assert (
        api._build_url("ISteamNews", "GetNewsForApp")
        == "https://api.steampowered.com/ISteamNews/GetNewsForApp/v1/"
    )


@pytest.mark.parametrize(
    ("base_url", "endpoint"),
    [
        ("https://store.steampowered.com/api", "appdetails"),
        ("https://store.steampowered.com/api/", "/appdetails"),
    ],
)
def test_build_store_url_joins_endpoint(base_url: str, endpoint: str) -> None:
    api = BaseAPI(Client(settings=offline_settings(STEAM_STORE_BASE_URL=base_url)))

    assert (
        api._build_store_url(endpoint)
        == "https://store.steampowered.com/api/appdetails"
    )


async def test_request_calls_built_url_with_api_key_by_default(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=SUMMARIES)

    data = await BaseAPI(client)._request(
        "ISteamUser", "GetPlayerSummaries", "v2", params={"steamids": STEAMID}
    )

    assert data == SUMMARIES
    sent = fake_steam.last
    assert (sent.method, sent.path) == ("GET", SUMMARIES_PATH)
    assert sent.params == {"steamids": STEAMID, "key": API_KEY}


async def test_request_passes_auth_type_through(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FAMILY_PATH, json=FAMILY)

    data = await BaseAPI(client)._request(
        "IFamilyGroupsService",
        "GetFamilyGroupForUser",
        params={"steamid": STEAMID},
        auth_type="access_token",
    )

    assert data == FAMILY
    assert fake_steam.last.path == FAMILY_PATH
    assert fake_steam.last.params == {"steamid": STEAMID, "access_token": ACCESS_TOKEN}


async def test_store_request_sends_no_credential_by_default(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", "/appdetails", json=APPDETAILS)
    params = {"appids": "570", "cc": "us", "l": "english"}

    data = await BaseAPI(client)._request_store("appdetails", params=params)

    assert data == APPDETAILS
    sent = fake_steam.last
    assert (sent.method, sent.path) == ("GET", f"{STORE_PREFIX}/appdetails")
    assert sent.params == params


# GetSteamLevel is GET-only on Steam; the other verbs just exercise _request.
@pytest.mark.parametrize("http_method", ["GET", "POST", "PUT", "DELETE"])
async def test_request_uses_the_given_verb(
    client: Client, fake_steam: FakeSteam, http_method: str
) -> None:
    fake_steam.api(http_method, STEAM_LEVEL_PATH, json=STEAM_LEVEL)

    data = await BaseAPI(client)._request(
        "IPlayerService",
        "GetSteamLevel",
        params={"steamid": STEAMID},
        http_method=http_method,
    )

    assert data == STEAM_LEVEL
    sent = fake_steam.last
    assert (sent.method, sent.path) == (http_method, STEAM_LEVEL_PATH)
    # Query or form body: where POST inputs belong is pinned down by #18 below.
    assert {**sent.query, **sent.form} == {"steamid": STEAMID, "key": API_KEY}


async def test_post_request_sends_inputs_in_form_body(
    client: Client, fake_steam: FakeSteam
) -> None:
    path = "/IFamilyGroupsService/SetFamilyCooldownOverrides/v1/"
    fake_steam.api("POST", path, json={"response": {}})
    inputs = {"family_groupid": "4223817", "cooldown_count": "1"}

    await BaseAPI(client)._request(
        "IFamilyGroupsService",
        "SetFamilyCooldownOverrides",
        params=inputs,
        auth_type="access_token",
        http_method="POST",
    )

    sent = fake_steam.last
    assert {name: sent.form.get(name) for name in inputs} == inputs


# -- request protocol (#10, #18) ----------------------------------------------

COOLDOWN_PATH = "/IFamilyGroupsService/SetFamilyCooldownOverrides/v1/"


async def post_cooldown(client: Client, fake_steam: FakeSteam) -> Any:
    """POST a family service method with the access token."""
    return await client.request(
        "POST",
        url_for(fake_steam, COOLDOWN_PATH),
        params={"family_groupid": "4223817", "cooldown_count": "1"},
        auth_type="access_token",
    )


async def test_post_sends_credential_in_form_body_not_query(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", COOLDOWN_PATH, json={"response": {}})

    await post_cooldown(client, fake_steam)

    sent = fake_steam.last
    assert sent.form.get("access_token") == ACCESS_TOKEN
    assert "access_token" not in sent.query
    assert sent.headers["Content-Type"] == "application/x-www-form-urlencoded"


async def test_post_form_encodes_booleans_as_digits(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", COOLDOWN_PATH, json={"response": {}})

    await client.request(
        "POST",
        url_for(fake_steam, COOLDOWN_PATH),
        params=[("include_own", True), ("include_free", False)],
        auth_type="none",
    )

    assert list(fake_steam.last.form.items()) == [
        ("include_own", "1"),
        ("include_free", "0"),
    ]


@pytest.mark.parametrize("status", [500, 502, 503])
async def test_post_is_not_retried_after_a_server_error(
    make_client: ClientFactory, fake_steam: FakeSteam, status: int
) -> None:
    fake_steam.api("POST", COOLDOWN_PATH, status=status, text="boom")
    client = make_client(MAX_RETRIES=2)

    with pytest.raises(SteamAPIError):
        await post_cooldown(client, fake_steam)

    assert len(fake_steam.requests) == 1


async def test_post_is_retried_after_a_rate_limit(
    make_client: ClientFactory, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", COOLDOWN_PATH, status=429, headers={"Retry-After": "0"})
    fake_steam.api("POST", COOLDOWN_PATH, json={"response": {}})
    client = make_client(MAX_RETRIES=1)

    assert await post_cooldown(client, fake_steam) == {"response": {}}
    assert len(fake_steam.requests) == 2


async def test_post_timeout_is_not_retried(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = make_client(MAX_RETRIES=2)
    calls = 0

    def timeout(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise asyncio.TimeoutError

    session = await client._get_session()
    monkeypatch.setattr(session, "request", timeout)

    with pytest.raises(NetworkError, match="timed out"):
        await client.request("POST", "http://steam.invalid/x", auth_type="none")

    assert calls == 1


async def test_get_timeout_is_retried(
    make_client: ClientFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = make_client(MAX_RETRIES=2)
    calls = 0

    def timeout(*args: Any, **kwargs: Any) -> Any:
        nonlocal calls
        calls += 1
        raise asyncio.TimeoutError

    session = await client._get_session()
    monkeypatch.setattr(session, "request", timeout)

    with pytest.raises(NetworkError):
        await client.request("GET", "http://steam.invalid/x", auth_type="none")

    assert calls == 3


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (403, AuthenticationError),
        (500, SteamAPIError),
        (502, ServiceUnavailableError),
        (504, ServiceUnavailableError),
    ],
)
async def test_http_status_exception_types(
    client: Client, fake_steam: FakeSteam, status: int, error: type[SteamAPIError]
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, **error_reply(status))

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    assert type(excinfo.value) is error
    assert excinfo.value.status_code == status


@pytest.mark.parametrize("status", [401, 403])
async def test_auth_status_without_credential_is_not_an_authentication_error(
    client: Client, fake_steam: FakeSteam, status: int
) -> None:
    # e.g. a private Steam Community inventory answers 403 to anonymous calls
    fake_steam.api("GET", NEWS_PATH, **error_reply(status))

    with pytest.raises(SteamAPIError) as excinfo:
        await client.request(
            "GET", url_for(fake_steam, NEWS_PATH), params=NEWS_PARAMS, auth_type="none"
        )

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == status


async def test_http_error_keeps_the_json_body(
    client: Client, fake_steam: FakeSteam
) -> None:
    body = {"playerstats": {"error": "Profile is not public", "success": False}}
    fake_steam.api("GET", SUMMARIES_PATH, status=400, json=body)

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.response_data == body


async def test_http_error_keeps_a_text_body(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, status=404, text="Not Found")

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.response_data == "Not Found"


async def test_credentialed_request_does_not_follow_redirects(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", SUMMARIES_PATH, status=302, text="", headers={"Location": NEWS_PATH}
    )
    fake_steam.api("GET", NEWS_PATH, json=NEWS)

    with pytest.raises(SteamAPIError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.status_code == 302
    assert [r.path for r in fake_steam.requests] == [SUMMARIES_PATH]


async def test_anonymous_request_follows_redirects(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", SUMMARIES_PATH, status=302, text="", headers={"Location": NEWS_PATH}
    )
    fake_steam.api("GET", NEWS_PATH, json=NEWS)

    data = await client.request(
        "GET", url_for(fake_steam, SUMMARIES_PATH), auth_type="none"
    )

    assert data == NEWS


async def test_retry_after_longer_than_max_retry_wait_is_not_waited_out(
    make_client: ClientFactory, fake_steam: FakeSteam, virtual_time: VirtualTime
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, status=429, headers={"Retry-After": "120"})
    client = make_client(MAX_RETRIES=3, MAX_RETRY_WAIT=60)

    with pytest.raises(RateLimitError) as excinfo:
        await get_summaries(client, fake_steam)

    assert excinfo.value.retry_after == 120
    assert virtual_time.sleeps == []
    assert len(fake_steam.requests) == 1


# -- x-eresult mapping (#18) --------------------------------------------------


@pytest.mark.parametrize(
    ("eresult", "error", "attempts"),
    [
        pytest.param(2, SteamAPIError, 1, id="fail"),
        pytest.param(8, SteamAPIError, 1, id="invalid-param"),
        pytest.param(15, AuthenticationError, 1, id="access-denied"),
        pytest.param(24, AuthenticationError, 1, id="insufficient-privilege"),
        pytest.param(20, ServiceUnavailableError, 3, id="service-unavailable"),
        pytest.param(84, RateLimitError, 3, id="rate-limit-exceeded"),
    ],
)
async def test_x_eresult_maps_to_exception_and_retry_policy(
    make_client: ClientFactory,
    fake_steam: FakeSteam,
    eresult: int,
    error: type[SteamAPIError],
    attempts: int,
) -> None:
    fake_steam.api(
        "GET",
        FAMILY_PATH,
        json={"response": {}},
        headers={"x-eresult": str(eresult), "x-error_message": "nope"},
    )
    client = make_client(MAX_RETRIES=2)

    with pytest.raises(SteamAPIError) as excinfo:
        await client.request(
            "GET", url_for(fake_steam, FAMILY_PATH), auth_type="access_token"
        )

    assert type(excinfo.value) is error
    assert excinfo.value.eresult == eresult
    assert excinfo.value.status_code == 200
    assert excinfo.value.response_data == {"response": {}}
    assert "nope" in str(excinfo.value)
    assert len(fake_steam.requests) == attempts


async def test_post_is_not_retried_after_a_transient_x_eresult(
    make_client: ClientFactory, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "POST", COOLDOWN_PATH, json={"response": {}}, headers={"x-eresult": "20"}
    )
    client = make_client(MAX_RETRIES=2)

    with pytest.raises(ServiceUnavailableError):
        await post_cooldown(client, fake_steam)

    assert len(fake_steam.requests) == 1


async def test_garbage_x_eresult_is_ignored(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS, headers={"x-eresult": "abc"})

    data = await client.request(
        "GET", url_for(fake_steam, NEWS_PATH), params=NEWS_PARAMS, auth_type="none"
    )

    assert data == NEWS


# -- configuration and external sessions (#10) ---------------------------------


async def test_connection_limit_comes_from_settings(
    make_client: ClientFactory,
) -> None:
    client = make_client(CONNECTION_LIMIT=7)

    session = await client._get_session()

    assert session.connector is not None
    assert session.connector.limit == 7


async def test_external_session_is_used_and_never_closed(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NEWS)
    async with aiohttp.ClientSession() as session:
        client = Client(settings=settings, session=session)

        data = await client.request(
            "GET", url_for(fake_steam, NEWS_PATH), params=NEWS_PARAMS, auth_type="none"
        )
        await client.close()

        assert data == NEWS
        assert client._session is session
        assert not session.closed
        assert fake_steam.last.headers["User-Agent"] == f"steamy-py/{__version__}"


async def test_closed_external_session_raises_configuration_error(
    settings: Settings,
) -> None:
    session = aiohttp.ClientSession()
    await session.close()
    client = Client(settings=settings, session=session)

    with pytest.raises(ConfigurationError):
        await client.request("GET", "http://steam.invalid/x", auth_type="none")


async def test_input_json_is_sent_as_one_parameter(
    client: Client, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STEAM_LEVEL_PATH, json=STEAM_LEVEL)

    await BaseAPI(client)._request(
        "IPlayerService",
        "GetSteamLevel",
        params={"format": "json"},
        input_json={"steamid": STEAMID, "appids": [440, 620]},
    )

    sent = fake_steam.last.params
    assert sent["format"] == "json"
    assert sent["input_json"] == f'{{"steamid":"{STEAMID}","appids":[440,620]}}'


def test_indexed_encodes_repeated_fields() -> None:
    assert BaseAPI._indexed("appids_filter", [440, 620]) == {
        "appids_filter[0]": "440",
        "appids_filter[1]": "620",
    }
