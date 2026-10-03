"""Tests for ``steam.library``: recently played games and last-played times.

GetRecentlyPlayedGames takes either credential (the API key when both are
set); ClientGetLastPlayedTimes is about the signed-in user and needs the
access token. Owned games are tested in ``test_game.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    InvalidSteamIDError,
    PrivateProfileError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
    SteamID,
)
from steamy_py.models.library import LastPlayedGame, RecentlyPlayedGame
from tests.fakesteam import ACCESS_TOKEN, API_KEY, STEAMID, FakeSteam, load_fixture

RECENT_PATH = "/IPlayerService/GetRecentlyPlayedGames/v1/"
LAST_PLAYED_PATH = "/IPlayerService/ClientGetLastPlayedTimes/v1/"

RECENT: dict[str, Any] = load_fixture("library_recently_played_games.json")
LAST_PLAYED: dict[str, Any] = load_fixture("library_last_played_times.json")
# What GetRecentlyPlayedGames answers for a public profile with no games
# played in the last two weeks.
NO_RECENT_GAMES: dict[str, Any] = {"response": {"total_count": 0}}

Call = Callable[[Steam], Awaitable[object]]

CALLS = [
    pytest.param(
        lambda steam: steam.library.get_recently_played_games(STEAMID),
        RECENT_PATH,
        RECENT,
        id="get_recently_played_games",
    ),
    pytest.param(
        lambda steam: steam.library.get_last_played_times(),
        LAST_PLAYED_PATH,
        LAST_PLAYED,
        id="get_last_played_times",
    ),
]

INVALID_STEAMIDS = [
    pytest.param("", id="empty"),
    pytest.param("robinwalker", id="vanity-name"),
    pytest.param("STEAM_0:0:84901", id="steam2-format"),
    pytest.param(STEAMID[:-1], id="16-digits"),
    pytest.param("103582791429521412", id="group-steamid"),
    pytest.param(True, id="bool"),
]


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


# -- shared by both methods ------------------------------------------------------


@pytest.mark.parametrize(("call", "path", "reply"), CALLS)
async def test_call_is_one_get_to_v1(
    steam: Steam, fake_steam: FakeSteam, call: Call, path: str, reply: dict[str, Any]
) -> None:
    fake_steam.api("GET", path, json=reply)

    await call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [("GET", path)]


@pytest.mark.parametrize(("call", "path", "reply"), CALLS)
async def test_http_error_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, call: Call, path: str, reply: dict[str, Any]
) -> None:
    fake_steam.api("GET", path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await call(steam)

    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    ("call", "path", "body", "message"),
    [
        pytest.param(
            lambda steam: steam.library.get_recently_played_games(STEAMID),
            RECENT_PATH,
            {"response": {"total_count": 1, "games": [{"appid": "portal"}]}},
            "Failed to get recently played games",
            id="recent-non-numeric-appid",
        ),
        pytest.param(
            lambda steam: steam.library.get_recently_played_games(STEAMID),
            RECENT_PATH,
            {"response": {"total_count": 1, "games": {"appid": 620}}},
            "Failed to get recently played games",
            id="recent-games-not-a-list",
        ),
        pytest.param(
            lambda steam: steam.library.get_recently_played_games(STEAMID),
            RECENT_PATH,
            {"response": []},
            "Failed to get recently played games",
            id="recent-response-not-an-object",
        ),
        # Not "no recent games": without a response object it is not known
        # whether the profile is private.
        pytest.param(
            lambda steam: steam.library.get_recently_played_games(STEAMID),
            RECENT_PATH,
            {},
            "Failed to get recently played games: no response object",
            id="recent-no-response-object",
        ),
        pytest.param(
            lambda steam: steam.library.get_recently_played_games(STEAMID),
            RECENT_PATH,
            {"total_count": 0, "games": []},
            "Failed to get recently played games: no response object",
            id="recent-body-not-wrapped-in-response",
        ),
        pytest.param(
            lambda steam: steam.library.get_last_played_times(),
            LAST_PLAYED_PATH,
            {"response": {"games": [{"appid": 620, "last_playtime": "yesterday"}]}},
            "Failed to get last played times",
            id="last-played-non-numeric-time",
        ),
        pytest.param(
            lambda steam: steam.library.get_last_played_times(),
            LAST_PLAYED_PATH,
            {"response": {"games": "none"}},
            "Failed to get last played times",
            id="last-played-games-not-a-list",
        ),
    ],
)
async def test_malformed_body_raises_response_parsing_error(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    body: dict[str, Any],
    message: str,
) -> None:
    fake_steam.api("GET", path, json=body)

    with pytest.raises(ResponseParsingError, match=message):
        await call(steam)


# -- IPlayerService/GetRecentlyPlayedGames ---------------------------------------


async def test_get_recently_played_games_sends_steamid_and_api_key(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", RECENT_PATH, json=RECENT)

    await steam.library.get_recently_played_games(STEAMID)

    assert fake_steam.last.params == {"steamid": STEAMID, "key": API_KEY}
    assert "Authorization" not in fake_steam.last.headers


async def test_get_recently_played_games_sends_count(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", RECENT_PATH, json=RECENT)

    await steam.library.get_recently_played_games(STEAMID, count=2)

    assert fake_steam.last.params == {"steamid": STEAMID, "count": "2", "key": API_KEY}


async def test_get_recently_played_games_uses_access_token_without_api_key(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", RECENT_PATH, json=RECENT)

    await token_only_steam.library.get_recently_played_games(STEAMID)

    assert fake_steam.last.params == {"steamid": STEAMID, "access_token": ACCESS_TOKEN}


async def test_get_recently_played_games_without_credentials_raises_before_request(
    settings: Settings, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", RECENT_PATH, json=RECENT)

    async with Steam(settings=settings) as steam:
        with pytest.raises(
            AuthenticationError, match="An API key or access token is required"
        ):
            await steam.library.get_recently_played_games(STEAMID)

    assert fake_steam.requests == []


@pytest.mark.parametrize("bad_id", INVALID_STEAMIDS)
async def test_get_recently_played_games_rejects_invalid_steamid_before_request(
    steam: Steam, fake_steam: FakeSteam, bad_id: Any
) -> None:
    fake_steam.api("GET", RECENT_PATH, json=RECENT)

    with pytest.raises(InvalidSteamIDError) as excinfo:
        await steam.library.get_recently_played_games(bad_id)

    assert excinfo.value.steamid == str(bad_id)
    assert fake_steam.requests == []


@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param(int(STEAMID), id="int"),
        pytest.param(SteamID(STEAMID), id="SteamID"),
    ],
)
async def test_get_recently_played_games_accepts_int_and_steamid(
    steam: Steam, fake_steam: FakeSteam, steamid: int | SteamID
) -> None:
    fake_steam.api("GET", RECENT_PATH, json=RECENT)

    await steam.library.get_recently_played_games(steamid)

    assert fake_steam.last.params["steamid"] == STEAMID


async def test_get_recently_played_games_parses_games(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", RECENT_PATH, json=RECENT)

    recent = await steam.library.get_recently_played_games(STEAMID, count=2)

    # total_count counts every game of the last two weeks, not just those sent.
    assert recent.total_count == 3
    assert all(isinstance(game, RecentlyPlayedGame) for game in recent.games)
    cs2, tf2 = recent.games
    assert tf2.model_dump() == {
        "appid": 440,
        "name": "Team Fortress 2",
        "playtime_2weeks": 95,
        "playtime_forever": 48213,
        "img_icon_url": "e3f595a92552da3d664ad00277fad2107345f743",
        "playtime_windows_forever": 47025,
        "playtime_mac_forever": 0,
        "playtime_linux_forever": 1093,
        "playtime_deck_forever": 95,
    }
    assert (cs2.appid, cs2.name, cs2.playtime_2weeks) == (730, "Counter-Strike 2", 1003)
    assert cs2.icon_url == (
        "https://media.steampowered.com/steamcommunity/public/images/apps/730/"
        "8dbc71957312bbd3baea65848b545be9eae2a355.jpg"
    )


async def test_get_recently_played_games_game_with_only_appid_gives_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        RECENT_PATH,
        json={"response": {"total_count": 1, "games": [{"appid": 620}]}},
    )

    [game] = (await steam.library.get_recently_played_games(STEAMID)).games

    assert game == RecentlyPlayedGame(appid=620)
    assert (game.name, game.playtime_2weeks, game.playtime_forever) == ("", 0, 0)
    assert game.icon_url is None


async def test_get_recently_played_games_public_profile_without_recent_games(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", RECENT_PATH, json=NO_RECENT_GAMES)

    recent = await steam.library.get_recently_played_games(STEAMID)

    assert (recent.total_count, recent.games) == (0, [])


async def test_get_recently_played_games_empty_response_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # What Steam answers when the game details are not public.
    fake_steam.api("GET", RECENT_PATH, json={"response": {}})

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.library.get_recently_played_games(STEAMID)

    assert excinfo.value.steamid == STEAMID
    assert excinfo.value.status_code == 403


# -- IPlayerService/ClientGetLastPlayedTimes -------------------------------------


async def test_get_last_played_times_sends_access_token_not_api_key(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LAST_PLAYED_PATH, json=LAST_PLAYED)

    await steam.library.get_last_played_times()

    assert fake_steam.last.params == {"access_token": ACCESS_TOKEN}
    assert "Authorization" not in fake_steam.last.headers


async def test_get_last_played_times_sends_min_last_played(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LAST_PLAYED_PATH, json=LAST_PLAYED)

    await steam.library.get_last_played_times(min_last_played=1727740800)

    assert fake_steam.last.params == {
        "min_last_played": "1727740800",
        "access_token": ACCESS_TOKEN,
    }


async def test_get_last_played_times_works_with_access_token_only(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LAST_PLAYED_PATH, json=LAST_PLAYED)

    games = await token_only_steam.library.get_last_played_times()

    assert [game.appid for game in games] == [440, 730, 220]
    assert fake_steam.last.params == {"access_token": ACCESS_TOKEN}


async def test_get_last_played_times_without_access_token_raises_before_request(
    key_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LAST_PLAYED_PATH, json=LAST_PLAYED)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await key_only_steam.library.get_last_played_times()

    assert fake_steam.requests == []


async def test_get_last_played_times_parses_every_field(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LAST_PLAYED_PATH, json=LAST_PLAYED)

    tf2, cs2, hl2 = await steam.library.get_last_played_times()

    assert all(isinstance(game, LastPlayedGame) for game in (tf2, cs2, hl2))
    # Every field Steam sent, and 0 for the ones it left out.
    assert tf2.model_dump() == {
        "playtime_mac_forever": 0,
        "first_mac_playtime": 0,
        "last_mac_playtime": 0,
        "playtime_disconnected": 0,
        **LAST_PLAYED["response"]["games"][0],
    }
    assert cs2.model_dump() == {
        "playtime_deck_forever": 0,
        "first_deck_playtime": 0,
        "last_deck_playtime": 0,
        **LAST_PLAYED["response"]["games"][1],
    }
    assert (hl2.appid, hl2.last_playtime, hl2.first_playtime) == (
        220,
        1726784163,
        1100736000,
    )
    assert hl2.playtime_2weeks == 0


async def test_get_last_played_times_empty_response_gives_no_games(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LAST_PLAYED_PATH, json={"response": {}})

    assert await steam.library.get_last_played_times() == []


async def test_get_last_played_times_game_with_only_appid_gives_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", LAST_PLAYED_PATH, json={"response": {"games": [{"appid": 620}]}}
    )

    [game] = await steam.library.get_last_played_times()

    assert game.model_dump() == {
        name: 620 if name == "appid" else 0 for name in LastPlayedGame.model_fields
    }


# -- IAccountPrivateAppsService/GetPrivateAppList ---------------------------------

# library_private_app_list.json is built from service_accountprivateapps.proto;
# no recorded reply was found.
PRIVATE_APPS_PATH = "/IAccountPrivateAppsService/GetPrivateAppList/v1/"
PRIVATE_APPS: dict[str, Any] = load_fixture("library_private_app_list.json")


async def test_get_private_app_list_is_one_get_to_v1_with_access_token_only(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PRIVATE_APPS_PATH, json=PRIVATE_APPS)

    await steam.library.get_private_app_list()

    assert [(r.method, r.path) for r in fake_steam.requests] == [
        ("GET", PRIVATE_APPS_PATH)
    ]
    # No inputs; the client has an API key too, but only the token is sent.
    assert fake_steam.last.params == {"access_token": ACCESS_TOKEN}
    assert "Authorization" not in fake_steam.last.headers


async def test_get_private_app_list_works_with_access_token_only(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PRIVATE_APPS_PATH, json=PRIVATE_APPS)

    appids = await token_only_steam.library.get_private_app_list()

    assert appids == [8930, 289070, 1145360]
    assert fake_steam.last.params == {"access_token": ACCESS_TOKEN}


async def test_get_private_app_list_without_access_token_raises_before_request(
    key_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PRIVATE_APPS_PATH, json=PRIVATE_APPS)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await key_only_steam.library.get_private_app_list()

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"response": {}}, id="empty-response"),
        pytest.param({"response": {"private_apps": {}}}, id="empty-private-apps"),
    ],
)
async def test_get_private_app_list_without_apps_is_empty(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.api("GET", PRIVATE_APPS_PATH, json=body)

    assert await steam.library.get_private_app_list() == []


async def test_get_private_app_list_http_error_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PRIVATE_APPS_PATH, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.library.get_private_app_list()

    assert excinfo.value.status_code == 500
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"response": {"private_apps": {"appids": ["portal"]}}},
            id="non-numeric-appid",
        ),
        pytest.param(
            {"response": {"private_apps": {"appids": 620}}}, id="appids-not-a-list"
        ),
        pytest.param({"response": {"private_apps": [620]}}, id="not-an-object"),
    ],
)
async def test_get_private_app_list_malformed_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.api("GET", PRIVATE_APPS_PATH, json=body)

    with pytest.raises(ResponseParsingError, match="Failed to get private app list"):
        await steam.library.get_private_app_list()
