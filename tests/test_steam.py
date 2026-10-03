"""Tests for the ``Steam`` facade: credentials, settings, lifecycle, health checks."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from steamy_py import (
    ConfigurationError,
    FamilyAPI,
    GameAPI,
    MarketAPI,
    PlayerAPI,
    Settings,
    StatsAPI,
    Steam,
)
from steamy_py.repos import BaseAPI
from tests.fakesteam import ACCESS_TOKEN, API_KEY, STEAMID, FakeSteam, RecordedRequest

# Variables ``Settings`` reads from the environment or a ``.env`` file.
SETTINGS_ENV_VARS = (
    "STEAM_API_BASE_URL",
    "STEAM_STORE_BASE_URL",
    "STEAM_COMMUNITY_BASE_URL",
    "REQUEST_TIMEOUT",
    "MAX_RETRIES",
    "RETRY_DELAY",
    "RATE_LIMIT_ENABLED",
    "REQUESTS_PER_SECOND",
    "LOG_LEVEL",
    "LOG_FORMAT",
)

# An IPlayerService method; service methods accept either credential.
PROBE_PATH = "/IPlayerService/GetSteamLevel/v1/"
PROBE_REPLY = {"response": {"player_level": 42}}

# ``test_connection()`` / ``get_api_key_info()`` currently probe the deprecated
# ISteamApps/GetAppList/v2 (#13). Real shape, trimmed from ~250k entries.
APP_LIST_PATH = "/ISteamApps/GetAppList/v2/"
APP_LIST = {
    "applist": {
        "apps": [
            {"appid": 10, "name": "Counter-Strike"},
            {"appid": 570, "name": "Dota 2"},
            {"appid": 730, "name": "Counter-Strike 2"},
        ]
    }
}

# The cheap, keyless connectivity check #13 suggests instead.
SERVER_INFO_PATH = "/ISteamWebAPIUtil/GetServerInfo/v1/"
SERVER_INFO = {"servertime": 1791025200, "servertimestring": "Sat Oct  3 11:00:00 2026"}

# What api.steampowered.com answers for a bad key.
FORBIDDEN_HTML = (
    "<html><head><title>Forbidden</title></head><body><h1>Forbidden</h1>"
    "Access is denied. Retrying will not help. Please verify your "
    "<pre>key=</pre> parameter.</body></html>"
)

CREDENTIAL_ENV = {"api_key": "STEAM_API_KEY", "access_token": "STEAM_ACCESS_TOKEN"}
QUERY_NAME = {"api_key": "key", "access_token": "access_token"}
EXPLICIT = {"api_key": API_KEY, "access_token": ACCESS_TOKEN}


@pytest.fixture
def clean_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run from an empty directory with no ``Settings`` variables set."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


@contextmanager
def bare_root_logger() -> Iterator[logging.Logger]:
    """Strip the root logger, like an application that has not set up logging.

    pytest attaches its capture handlers to the root logger for each test phase,
    so this must run inside the test body rather than in a fixture.
    """
    root = logging.getLogger()
    saved_handlers = root.handlers[:]
    saved_level = root.level
    root.handlers.clear()
    try:
        yield root
    finally:
        for handler in root.handlers:
            if handler not in saved_handlers:
                handler.close()
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)


async def send_probe(
    steam: Steam, fake_steam: FakeSteam, auth_type: str
) -> RecordedRequest:
    """Send one request through ``steam``'s client; return what the server saw."""
    fake_steam.api("GET", PROBE_PATH, json=PROBE_REPLY)
    data = await steam.client.request(
        "GET",
        fake_steam.url + PROBE_PATH,
        params={"steamid": STEAMID},
        auth_type=auth_type,
    )
    assert data == PROBE_REPLY
    return fake_steam.last


# -- credentials ---------------------------------------------------------------


@pytest.mark.parametrize(
    "credentials",
    [
        pytest.param({}, id="none"),
        pytest.param({"api_key": None, "access_token": None}, id="explicit-none"),
        pytest.param({"api_key": ""}, id="empty-key"),
        pytest.param({"access_token": ""}, id="empty-token"),
        pytest.param({"api_key": "", "access_token": ""}, id="both-empty"),
    ],
)
def test_missing_credentials_raise_configuration_error(
    clean_config: Path, credentials: dict[str, Any]
) -> None:
    with pytest.raises(ConfigurationError, match=r"STEAM_API_KEY.*STEAM_ACCESS_TOKEN"):
        Steam(**credentials)


@pytest.mark.parametrize("credential", ["api_key", "access_token"])
async def test_credential_falls_back_to_env_var(
    monkeypatch: pytest.MonkeyPatch,
    fake_steam: FakeSteam,
    settings: Settings,
    credential: str,
) -> None:
    monkeypatch.setenv(CREDENTIAL_ENV[credential], "from-env-123")

    async with Steam(settings=settings) as steam:
        request = await send_probe(steam, fake_steam, credential)

    assert getattr(steam.client, credential) == "from-env-123"
    assert request.params == {
        "steamid": STEAMID,
        QUERY_NAME[credential]: "from-env-123",
    }


@pytest.mark.parametrize("credential", ["api_key", "access_token"])
async def test_explicit_credential_wins_over_env_var(
    monkeypatch: pytest.MonkeyPatch,
    fake_steam: FakeSteam,
    settings: Settings,
    credential: str,
) -> None:
    monkeypatch.setenv(CREDENTIAL_ENV[credential], "from-env-123")

    async with Steam(settings=settings, **{credential: EXPLICIT[credential]}) as steam:
        request = await send_probe(steam, fake_steam, credential)

    assert getattr(steam.client, credential) == EXPLICIT[credential]
    assert request.params[QUERY_NAME[credential]] == EXPLICIT[credential]


def test_each_credential_falls_back_independently(
    monkeypatch: pytest.MonkeyPatch, settings: Settings
) -> None:
    monkeypatch.setenv("STEAM_ACCESS_TOKEN", "token-from-env")

    steam = Steam(api_key=API_KEY, settings=settings)

    assert steam.client.api_key == API_KEY
    assert steam.client.access_token == "token-from-env"


@pytest.mark.parametrize("credential", ["api_key", "access_token"])
def test_a_single_credential_is_enough(settings: Settings, credential: str) -> None:
    steam = Steam(settings=settings, **{credential: EXPLICIT[credential]})

    other = "access_token" if credential == "api_key" else "api_key"
    assert getattr(steam.client, credential) == EXPLICIT[credential]
    assert getattr(steam.client, other) is None


# -- settings ------------------------------------------------------------------


def test_explicit_settings_object_is_used_as_is(settings: Settings) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)

    assert steam.client.settings is settings


def test_settings_kwargs_are_forwarded_to_settings(clean_config: Path) -> None:
    steam = Steam(api_key=API_KEY, MAX_RETRIES=5, REQUEST_TIMEOUT=12)

    assert steam.client.settings.MAX_RETRIES == 5
    assert steam.client.settings.REQUEST_TIMEOUT == 12


async def test_settings_kwargs_drive_the_requests(
    clean_config: Path, fake_steam: FakeSteam
) -> None:
    path = "/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
    fake_steam.api("GET", path, status=503, text="Service Unavailable")
    fake_steam.api("GET", path, status=503, text="Service Unavailable")
    fake_steam.api(
        "GET", path, json={"response": {"player_count": 1043578, "result": 1}}
    )

    async with Steam(
        api_key=API_KEY,
        STEAM_API_BASE_URL=fake_steam.url,
        RATE_LIMIT_ENABLED=False,
        MAX_RETRIES=2,
        RETRY_DELAY=0.0,
    ) as steam:
        count = await steam.stats.get_current_players(730)

    assert count.player_count == 1043578
    assert [r.params["appid"] for r in fake_steam.requests_to(path)] == ["730"] * 3


def test_default_settings_target_the_real_steam_hosts(clean_config: Path) -> None:
    settings = Steam(api_key=API_KEY).client.settings

    assert settings.STEAM_API_BASE_URL == "https://api.steampowered.com"
    assert settings.STEAM_STORE_BASE_URL == "https://store.steampowered.com/api"
    assert settings.STEAM_COMMUNITY_BASE_URL == "https://steamcommunity.com"


# -- repositories --------------------------------------------------------------


@pytest.mark.parametrize(
    ("attribute", "api_class"),
    [
        ("player", PlayerAPI),
        ("games", GameAPI),
        ("market", MarketAPI),
        ("stats", StatsAPI),
        ("family", FamilyAPI),
    ],
)
def test_repositories_share_the_client(
    settings: Settings, attribute: str, api_class: type[BaseAPI]
) -> None:
    steam = Steam(api_key=API_KEY, access_token=ACCESS_TOKEN, settings=settings)

    repo = getattr(steam, attribute)

    assert type(repo) is api_class
    assert repo.client is steam.client


# -- lifecycle -----------------------------------------------------------------


def test_new_client_is_not_connected(settings: Settings) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)

    assert steam.is_connected is False


async def test_context_manager_connects_and_closes(settings: Settings) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)

    async with steam as entered:
        assert entered is steam
        assert steam.is_connected is True

    assert steam.is_connected is False


async def test_context_manager_closes_when_the_body_raises(settings: Settings) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)

    with pytest.raises(RuntimeError, match="boom"):
        async with steam:
            raise RuntimeError("boom")

    assert steam.is_connected is False


async def test_connect_is_idempotent(settings: Settings) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)
    try:
        await steam.connect()
        session = steam.client._session
        await steam.connect()

        assert steam.is_connected is True
        assert steam.client._session is session
    finally:
        await steam.close()


async def test_close_is_idempotent(settings: Settings) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)
    await steam.connect()

    await steam.close()
    await steam.close()

    assert steam.is_connected is False


async def test_close_before_connect_is_a_no_op(settings: Settings) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)

    await steam.close()

    assert steam.is_connected is False


async def test_connect_after_close_reconnects(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)
    async with steam:
        pass

    async with steam:
        assert steam.is_connected is True
        request = await send_probe(steam, fake_steam, "api_key")

    assert request.params["key"] == API_KEY


async def test_first_request_connects_lazily(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)
    try:
        request = await send_probe(steam, fake_steam, "api_key")

        assert steam.is_connected is True
        assert request.path == PROBE_PATH
    finally:
        await steam.close()


@pytest.mark.xfail(
    reason="#10: requests after close() fail instead of reconnecting",
    raises=RuntimeError,
)
async def test_request_after_close_reconnects_lazily(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)
    async with steam:
        pass
    try:
        request = await send_probe(steam, fake_steam, "api_key")

        assert request.path == PROBE_PATH
    finally:
        await steam.close()


# -- repr ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "credentials",
    [
        pytest.param({"api_key": API_KEY}, id="key"),
        pytest.param({"access_token": ACCESS_TOKEN}, id="token"),
        pytest.param({"api_key": API_KEY, "access_token": ACCESS_TOKEN}, id="both"),
    ],
)
def test_repr_hides_credentials_and_reports_disconnected(
    settings: Settings, credentials: dict[str, str]
) -> None:
    text = repr(Steam(settings=settings, **credentials))

    assert API_KEY not in text
    assert ACCESS_TOKEN not in text
    assert "status='disconnected'" in text


async def test_repr_reports_connected(steam: Steam) -> None:
    text = repr(steam)

    assert "status='connected'" in text
    assert API_KEY not in text
    assert ACCESS_TOKEN not in text


# -- test_connection() / get_api_key_info() ------------------------------------


async def test_test_connection_succeeds_when_steam_answers(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # #13: this probes the deprecated ISteamApps/GetAppList/v2.
    fake_steam.api("GET", APP_LIST_PATH, json=APP_LIST)

    assert await steam.test_connection() is True

    assert fake_steam.last.method == "GET"
    assert fake_steam.last.path == APP_LIST_PATH
    assert fake_steam.last.params == {"key": API_KEY}


async def test_test_connection_connects_when_needed(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    fake_steam.api("GET", APP_LIST_PATH, json=APP_LIST)
    steam = Steam(api_key=API_KEY, settings=settings)
    try:
        assert await steam.test_connection() is True
        assert steam.is_connected is True
    finally:
        await steam.close()


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param(
            {
                "status": 500,
                "text": "<html><body><h1>Internal Server Error</h1></body></html>",
                "content_type": "text/html",
            },
            id="http-500",
        ),
        pytest.param(
            {"status": 403, "text": FORBIDDEN_HTML, "content_type": "text/html"},
            id="bad-key-403",
        ),
        pytest.param(
            {"status": 200, "text": "<html>Error</html>", "content_type": "text/html"},
            id="not-json",
        ),
        pytest.param({"status": 200, "json": {}}, id="unexpected-shape"),
        pytest.param(None, id="endpoint-gone-404"),
    ],
)
async def test_test_connection_returns_false_on_failure(
    steam: Steam, fake_steam: FakeSteam, reply: dict[str, Any] | None
) -> None:
    if reply is not None:
        fake_steam.api("GET", APP_LIST_PATH, **reply)

    assert await steam.test_connection() is False

    assert [r.path for r in fake_steam.requests] == [APP_LIST_PATH]


async def test_get_api_key_info_reports_a_working_key(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # #13: this downloads the deprecated ISteamApps/GetAppList/v2.
    fake_steam.api("GET", APP_LIST_PATH, json=APP_LIST)

    info = await steam.get_api_key_info()

    assert info == {
        "valid": True,
        "connected": True,
        "test_result": "Successfully retrieved 3 Steam applications",
    }
    assert fake_steam.last.params == {"key": API_KEY}


async def test_get_api_key_info_reports_a_rejected_key_without_leaking_it(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", APP_LIST_PATH, status=403, text=FORBIDDEN_HTML, content_type="text/html"
    )

    info = await steam.get_api_key_info()

    assert info["valid"] is False
    assert info["connected"] is True
    assert "403" in info["error"]
    assert API_KEY not in info["error"]


@pytest.mark.xfail(
    reason="#13: health checks download the deprecated ISteamApps/GetAppList/v2",
    raises=AssertionError,
)
@pytest.mark.parametrize("check", ["test_connection", "get_api_key_info"])
async def test_health_checks_avoid_the_deprecated_app_list(
    steam: Steam, fake_steam: FakeSteam, check: str
) -> None:
    fake_steam.api("GET", SERVER_INFO_PATH, json=SERVER_INFO)
    fake_steam.api("GET", APP_LIST_PATH, json=APP_LIST)

    await getattr(steam, check)()

    assert fake_steam.requests_to(APP_LIST_PATH) == []


@pytest.mark.xfail(
    reason="#13: test_connection always uses the API key path",
    raises=AssertionError,
)
async def test_test_connection_uses_the_access_token_when_there_is_no_key(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    fake_steam.api("GET", SERVER_INFO_PATH, json=SERVER_INFO)

    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as steam:
        await steam.test_connection()

    assert any(
        r.params.get("access_token") == ACCESS_TOKEN for r in fake_steam.requests
    )


# -- process-wide side effects (#12) -------------------------------------------


@pytest.mark.xfail(
    reason="#12: Client.__init__ calls logging.basicConfig()", raises=AssertionError
)
def test_constructing_steam_leaves_the_root_logger_alone(settings: Settings) -> None:
    with bare_root_logger() as root:
        level = root.level
        Steam(api_key=API_KEY, settings=settings)

        assert root.handlers == []
        assert root.level == level


@pytest.mark.xfail(
    reason="#12: LOG_LEVEL=info in the app's environment crashes Steam()",
    raises=TypeError,
)
def test_lowercase_log_level_in_the_environment_does_not_break_steam(
    clean_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "info")

    with bare_root_logger():
        steam = Steam(api_key=API_KEY)

    assert steam.client.api_key == API_KEY
