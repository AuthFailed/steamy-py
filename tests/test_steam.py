"""Tests for the ``Steam`` facade: credentials, settings, lifecycle, health checks."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from steamy_py import (
    AuthAPI,
    AuthenticationError,
    ConfigurationError,
    EconomyAPI,
    FamilyAPI,
    FriendsAPI,
    GameAPI,
    LibraryAPI,
    MarketAPI,
    NotificationsAPI,
    PlayerAPI,
    ServersAPI,
    Settings,
    StatsAPI,
    Steam,
    StoreAPI,
    UsersAPI,
    UtilAPI,
    WishlistAPI,
    WorkshopAPI,
)
from steamy_py.repos import BaseAPI
from tests.fakesteam import ACCESS_TOKEN, API_KEY, STEAMID, FakeSteam, RecordedRequest

# Variables ``Settings`` reads from the environment.
SETTINGS_ENV_VARS = tuple(f"STEAMY_{name}" for name in Settings.model_fields)

# An IPlayerService method; service methods accept either credential.
PROBE_PATH = "/IPlayerService/GetSteamLevel/v1/"
PROBE_REPLY = {"response": {"player_level": 42}}

# ``test_connection()`` / ``get_api_key_info()`` first check Steam is reachable
# with the keyless ISteamWebAPIUtil/GetServerInfo, then make one cheap call
# with the configured credential (#13).
SERVER_INFO_PATH = "/ISteamWebAPIUtil/GetServerInfo/v1/"
SERVER_INFO = {"servertime": 1791025200, "servertimestring": "Sat Oct  3 11:00:00 2026"}
STORE_APP_LIST_PATH = "/IStoreService/GetAppList/v1/"
STORE_APP_LIST = {
    "response": {
        "apps": [
            {
                "appid": 10,
                "name": "Counter-Strike",
                "last_modified": 1745368572,
                "price_change_number": 21319021,
            }
        ],
        "have_more_results": True,
        "last_appid": 10,
    }
}
# The deprecated endpoint the health checks must no longer download.
OLD_APP_LIST_PATH = "/ISteamApps/GetAppList/v2/"

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
async def test_client_without_credentials_calls_keyless_endpoints(
    clean_config: Path,
    fake_steam: FakeSteam,
    settings: Settings,
    credentials: dict[str, Any],
) -> None:
    fake_steam.api(
        "GET",
        "/ISteamUserStats/GetNumberOfCurrentPlayers/v1/",
        json={"response": {"player_count": 1043578, "result": 1}},
    )

    async with Steam(settings=settings, **credentials) as steam:
        count = await steam.stats.get_current_players(730)
        with pytest.raises(AuthenticationError, match="API key"):
            await steam.users.get_player_summary(STEAMID)

    assert count.player_count == 1043578
    assert len(fake_steam.requests) == 1


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


def test_settings_kwargs_win_over_the_environment(
    clean_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STEAMY_MAX_RETRIES", "1")

    steam = Steam(api_key=API_KEY, MAX_RETRIES=5)

    assert steam.client.settings.MAX_RETRIES == 5


@pytest.mark.parametrize("name", ["MAX_RETRIES", "max_retries"])
def test_settings_kwargs_apply_on_top_of_a_settings_object(
    settings: Settings, name: str
) -> None:
    assert settings.MAX_RETRIES == 0

    steam = Steam(api_key=API_KEY, settings=settings, **{name: 5})

    assert steam.client.settings.MAX_RETRIES == 5
    assert steam.client.settings.STEAM_API_BASE_URL == settings.STEAM_API_BASE_URL
    assert settings.MAX_RETRIES == 0


def test_lowercase_settings_kwargs_are_accepted(clean_config: Path) -> None:
    steam = Steam(api_key=API_KEY, max_retries=5)

    assert steam.client.settings.MAX_RETRIES == 5


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param({"MAX_RETRYS": 5}, id="misspelled"),
        pytest.param({"MAX_RETRIES": "many"}, id="invalid-value"),
    ],
)
def test_bad_settings_kwargs_raise_configuration_error(
    clean_config: Path, kwargs: dict[str, Any]
) -> None:
    with pytest.raises(ConfigurationError, match="Invalid settings"):
        Steam(api_key=API_KEY, **kwargs)


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
    # GetNumberOfCurrentPlayers needs no key, so none is sent.
    assert [r.params for r in fake_steam.requests_to(path)] == [{"appid": "730"}] * 3


def test_default_settings_target_the_real_steam_hosts(clean_config: Path) -> None:
    settings = Steam(api_key=API_KEY).client.settings

    assert settings.STEAM_API_BASE_URL == "https://api.steampowered.com"
    assert settings.STEAM_STORE_BASE_URL == "https://store.steampowered.com/api"
    assert settings.STEAM_COMMUNITY_BASE_URL == "https://steamcommunity.com"


# -- repositories --------------------------------------------------------------


@pytest.mark.parametrize(
    ("attribute", "api_class"),
    [
        ("users", UsersAPI),
        ("library", LibraryAPI),
        ("stats", StatsAPI),
        ("store", StoreAPI),
        ("wishlist", WishlistAPI),
        ("workshop", WorkshopAPI),
        ("economy", EconomyAPI),
        ("market", MarketAPI),
        ("family", FamilyAPI),
        ("friends", FriendsAPI),
        ("notifications", NotificationsAPI),
        ("servers", ServersAPI),
        ("auth", AuthAPI),
        ("util", UtilAPI),
        ("games", GameAPI),
    ],
)
def test_repositories_share_the_client(
    settings: Settings, attribute: str, api_class: type[BaseAPI]
) -> None:
    steam = Steam(api_key=API_KEY, access_token=ACCESS_TOKEN, settings=settings)

    repo = getattr(steam, attribute)

    assert type(repo) is api_class
    assert repo.client is steam.client


def test_player_is_a_deprecated_alias_of_users(settings: Settings) -> None:
    steam = Steam(api_key=API_KEY, settings=settings)

    with pytest.warns(DeprecationWarning, match=r"Steam\.users"):
        assert steam.player is steam.users
    assert PlayerAPI is UsersAPI


@pytest.mark.parametrize(
    ("call", "path", "reply", "new_name"),
    [
        pytest.param(
            lambda steam: steam.games.get_owned_games(STEAMID),
            "/IPlayerService/GetOwnedGames/v1/",
            {"response": {"game_count": 0}},
            "Steam.library.get_owned_games",
            id="get_owned_games",
        ),
        pytest.param(
            lambda steam: steam.games.get_app_list_page(),
            "/IStoreService/GetAppList/v1/",
            {"response": {"apps": []}},
            "Steam.store.get_app_list_page",
            id="get_app_list_page",
        ),
        pytest.param(
            lambda steam: steam.games.get_app_list(),
            "/IStoreService/GetAppList/v1/",
            {"response": {"apps": []}},
            "Steam.store.get_app_list",
            id="get_app_list",
        ),
        pytest.param(
            lambda steam: steam.games.get_schema_for_game(440),
            "/ISteamUserStats/GetSchemaForGame/v2/",
            {"game": {"gameName": "TF2"}},
            "Steam.stats.get_schema_for_game",
            id="get_schema_for_game",
        ),
        pytest.param(
            lambda steam: steam.games.get_player_achievements(STEAMID, 440),
            "/ISteamUserStats/GetPlayerAchievements/v1/",
            {"playerstats": {"steamID": STEAMID, "gameName": "TF2", "success": True}},
            "Steam.stats.get_player_achievements",
            id="get_player_achievements",
        ),
        pytest.param(
            lambda steam: steam.games.search_games("x", owned_games=[]),
            None,
            None,
            "Steam.store.search_games",
            id="search_games",
        ),
        pytest.param(
            lambda steam: steam.stats.get_news_for_app(440),
            "/ISteamNews/GetNewsForApp/v2/",
            {"appnews": {"appid": 440, "newsitems": [], "count": 0}},
            "Steam.store.get_news_for_app",
            id="stats.get_news_for_app",
        ),
    ],
)
async def test_moved_methods_warn_and_still_work(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Any,
    path: str | None,
    reply: Any,
    new_name: str,
) -> None:
    if path is not None:
        fake_steam.api("GET", path, json=reply)

    with pytest.warns(DeprecationWarning, match=new_name.replace(".", r"\.")):
        await call(steam)

    assert len(fake_steam.requests) == (0 if path is None else 1)


async def test_moved_app_details_and_iter_app_list_warn(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", "/appdetails", json={"620": {"success": False}})
    fake_steam.api("GET", "/IStoreService/GetAppList/v1/", json={"response": {}})

    with pytest.warns(DeprecationWarning, match="Steam.store.get_app_details"):
        assert await steam.games.get_app_details(620) is None
    with pytest.warns(DeprecationWarning, match="Steam.store.iter_app_list"):
        assert [app async for app in steam.games.iter_app_list()] == []


async def test_moved_inventory_methods_warn_and_still_work(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    path = f"/inventory/{STEAMID}/730/2"
    fake_steam.community(
        "GET", path, json={"assets": [], "descriptions": [], "success": 1}
    )

    with pytest.warns(DeprecationWarning, match="Steam.economy.get_inventory"):
        await steam.market.get_inventory(STEAMID, 730)
    with pytest.warns(DeprecationWarning, match="Steam.economy.get_full_inventory"):
        await steam.market.get_full_inventory(STEAMID, 730)
    with pytest.warns(DeprecationWarning, match="Steam.economy.iter_inventory_pages"):
        pages = [page async for page in steam.market.iter_inventory_pages(STEAMID, 730)]

    assert len(pages) == 1


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


def test_repr_does_not_claim_an_api_key_for_a_token_only_client(
    settings: Settings,
) -> None:
    text = repr(Steam(access_token=ACCESS_TOKEN, settings=settings))

    assert "api_key" not in text


async def test_repr_reports_connected(steam: Steam) -> None:
    text = repr(steam)

    assert "status='connected'" in text
    assert API_KEY not in text
    assert ACCESS_TOKEN not in text


# -- test_connection() / get_api_key_info() ------------------------------------


def serve_health_check(fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", SERVER_INFO_PATH, json=SERVER_INFO)
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=STORE_APP_LIST)


async def test_test_connection_succeeds_when_steam_answers(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    serve_health_check(fake_steam)

    assert await steam.test_connection() is True

    server_info, credential_check = fake_steam.requests
    assert server_info.path == SERVER_INFO_PATH
    assert server_info.params == {}
    assert credential_check.method == "GET"
    assert credential_check.path == STORE_APP_LIST_PATH
    assert credential_check.params == {
        "input_json": '{"max_results":1}',
        "key": API_KEY,
    }


async def test_test_connection_connects_when_needed(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    serve_health_check(fake_steam)
    steam = Steam(api_key=API_KEY, settings=settings)
    try:
        assert await steam.test_connection() is True
        assert steam.is_connected is True
    finally:
        await steam.close()


FAILED_REPLIES = [
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
]


@pytest.mark.parametrize("reply", FAILED_REPLIES)
async def test_test_connection_returns_false_when_the_credential_check_fails(
    steam: Steam, fake_steam: FakeSteam, reply: dict[str, Any] | None
) -> None:
    fake_steam.api("GET", SERVER_INFO_PATH, json=SERVER_INFO)
    if reply is not None:
        fake_steam.api("GET", STORE_APP_LIST_PATH, **reply)

    assert await steam.test_connection() is False

    assert [r.path for r in fake_steam.requests] == [
        SERVER_INFO_PATH,
        STORE_APP_LIST_PATH,
    ]


@pytest.mark.parametrize("reply", FAILED_REPLIES)
async def test_test_connection_returns_false_when_steam_is_unreachable(
    steam: Steam, fake_steam: FakeSteam, reply: dict[str, Any] | None
) -> None:
    if reply is not None:
        fake_steam.api("GET", SERVER_INFO_PATH, **reply)
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=STORE_APP_LIST)

    assert await steam.test_connection() is False

    assert [r.path for r in fake_steam.requests] == [SERVER_INFO_PATH]


async def test_get_api_key_info_reports_a_working_key(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    serve_health_check(fake_steam)

    info = await steam.get_api_key_info()

    assert info == {
        "valid": True,
        "connected": True,
        "test_result": "API key accepted by Steam",
    }
    assert fake_steam.last.path == STORE_APP_LIST_PATH
    assert fake_steam.last.params["key"] == API_KEY


async def test_get_api_key_info_reports_a_rejected_key_without_leaking_it(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SERVER_INFO_PATH, json=SERVER_INFO)
    fake_steam.api(
        "GET",
        STORE_APP_LIST_PATH,
        status=403,
        text=FORBIDDEN_HTML,
        content_type="text/html",
    )

    info = await steam.get_api_key_info()

    assert info["valid"] is False
    assert info["connected"] is True
    assert "403" in info["error"]
    assert API_KEY not in info["error"]
    assert ACCESS_TOKEN not in info["error"]


async def test_get_api_key_info_connects_when_needed(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    serve_health_check(fake_steam)
    steam = Steam(api_key=API_KEY, settings=settings)
    try:
        info = await steam.get_api_key_info()

        assert info["valid"] is True
        assert steam.is_connected is True
    finally:
        await steam.close()


async def test_test_connection_failure_does_not_log_credentials(
    steam: Steam, fake_steam: FakeSteam, caplog: pytest.LogCaptureFixture
) -> None:
    fake_steam.api("GET", SERVER_INFO_PATH, json=SERVER_INFO)
    fake_steam.api(
        "GET",
        STORE_APP_LIST_PATH,
        status=403,
        text=FORBIDDEN_HTML,
        content_type="text/html",
    )

    with caplog.at_level(logging.DEBUG, logger="steamy_py"):
        assert await steam.test_connection() is False

    assert "connection test failed" in caplog.text
    assert API_KEY not in caplog.text
    assert ACCESS_TOKEN not in caplog.text


@pytest.mark.parametrize("check", ["test_connection", "get_api_key_info"])
async def test_health_checks_avoid_the_deprecated_app_list(
    steam: Steam, fake_steam: FakeSteam, check: str
) -> None:
    serve_health_check(fake_steam)
    fake_steam.api("GET", OLD_APP_LIST_PATH, json={"applist": {"apps": []}})

    await getattr(steam, check)()

    assert fake_steam.requests_to(OLD_APP_LIST_PATH) == []
    assert fake_steam.requests, "the health check must still reach Steam"


async def test_test_connection_uses_the_access_token_when_there_is_no_key(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    serve_health_check(fake_steam)

    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as steam:
        assert await steam.test_connection() is True

    assert fake_steam.last.params["access_token"] == ACCESS_TOKEN
    assert "key" not in fake_steam.last.params


# -- process-wide side effects (#12) -------------------------------------------


def test_constructing_steam_leaves_the_root_logger_alone(settings: Settings) -> None:
    with bare_root_logger() as root:
        level = root.level
        Steam(api_key=API_KEY, settings=settings)

        assert root.handlers == []
        assert root.level == level


def test_lowercase_log_level_in_the_environment_does_not_break_steam(
    clean_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LOG_LEVEL", "info")

    with bare_root_logger():
        steam = Steam(api_key=API_KEY)

    assert steam.client.api_key == API_KEY
