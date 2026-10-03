"""Tests for ``GameAPI``: owned games, achievements, schemas, store and app list."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import pytest

from steamy_py import (
    GameNotFoundError,
    InvalidAppIDError,
    InvalidSteamIDError,
    OwnedGame,
    PrivateProfileError,
    Settings,
    Steam,
    SteamAPIError,
    SteamApp,
)
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    STORE_PREFIX,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

OWNED_GAMES_PATH = "/IPlayerService/GetOwnedGames/v1/"
ACHIEVEMENTS_PATH = "/ISteamUserStats/GetPlayerAchievements/v1/"
SCHEMA_PATH = "/ISteamUserStats/GetSchemaForGame/v2/"
STORE_APP_LIST_PATH = "/IStoreService/GetAppList/v1/"
APP_DETAILS_PATH = STORE_PREFIX + "/appdetails"

NO_GAMES: dict[str, Any] = {"response": {"game_count": 0}}
NO_ACHIEVEMENTS: dict[str, Any] = {
    "playerstats": {"steamID": STEAMID, "gameName": "Half-Life 2", "success": True}
}
TF2_SCHEMA_STUB: dict[str, Any] = {
    "game": {"gameName": "Team Fortress 2", "gameVersion": "142"}
}
UNKNOWN_APP_DETAILS: dict[str, Any] = {"9999999": {"success": False}}

# Real shape of IStoreService/GetAppList/v1, trimmed from ~200k entries.
STORE_APP_LIST: dict[str, Any] = {
    "response": {
        "apps": [
            {
                "appid": 10,
                "name": "Counter-Strike",
                "last_modified": 1745368572,
                "price_change_number": 21319021,
            },
            {
                "appid": 400,
                "name": "Portal",
                "last_modified": 1745363075,
                "price_change_number": 21318872,
            },
            {
                "appid": 620,
                "name": "Portal 2",
                "last_modified": 1745363004,
                "price_change_number": 21318872,
            },
            {
                "appid": 730,
                "name": "Counter-Strike 2",
                "last_modified": 1759184524,
                "price_change_number": 31125813,
            },
        ]
    }
}
EXPECTED_APPS = [
    (10, "Counter-Strike"),
    (400, "Portal"),
    (620, "Portal 2"),
    (730, "Counter-Strike 2"),
]

Call = Callable[[Steam], Awaitable[object]]


def assert_sent_with_api_key(request: RecordedRequest, path: str) -> None:
    """``request`` is a GET to ``path`` carrying the API key, not the token."""
    assert request.method == "GET"
    assert request.path == path
    assert request.query.getall("key") == [API_KEY]
    assert "access_token" not in request.query


def owned_game(appid: int, **fields: Any) -> dict[str, Any]:
    """A GetOwnedGames entry as Steam sends it without ``include_appinfo``."""
    return {
        "appid": appid,
        "playtime_forever": 0,
        "playtime_windows_forever": 0,
        "playtime_mac_forever": 0,
        "playtime_linux_forever": 0,
        "playtime_deck_forever": 0,
        "rtime_last_played": 0,
        "playtime_disconnected": 0,
        **fields,
    }


# Every method with a reply that parses, for the cross-cutting checks.
ENDPOINTS = [
    pytest.param(
        lambda steam: steam.games.get_owned_games(STEAMID),
        OWNED_GAMES_PATH,
        NO_GAMES,
        id="get_owned_games",
    ),
    pytest.param(
        lambda steam: steam.games.get_player_achievements(STEAMID, 220),
        ACHIEVEMENTS_PATH,
        NO_ACHIEVEMENTS,
        id="get_player_achievements",
    ),
    pytest.param(
        lambda steam: steam.games.get_schema_for_game(440),
        SCHEMA_PATH,
        TF2_SCHEMA_STUB,
        id="get_schema_for_game",
    ),
    pytest.param(
        lambda steam: steam.games.get_app_details(9999999),
        APP_DETAILS_PATH,
        UNKNOWN_APP_DETAILS,
        id="get_app_details",
    ),
    pytest.param(
        lambda steam: steam.games.get_app_list(),
        STORE_APP_LIST_PATH,
        STORE_APP_LIST,
        id="get_app_list",
    ),
]

# Methods for which Steam requires the Web API key.
KEYED_ENDPOINTS = [
    p
    for p in ENDPOINTS
    if p.id in {"get_owned_games", "get_player_achievements", "get_schema_for_game"}
]

STEAMID_CALLS = [
    pytest.param(
        lambda steam, steamid: steam.games.get_owned_games(steamid),
        OWNED_GAMES_PATH,
        NO_GAMES,
        id="get_owned_games",
    ),
    pytest.param(
        lambda steam, steamid: steam.games.get_player_achievements(steamid, 220),
        ACHIEVEMENTS_PATH,
        NO_ACHIEVEMENTS,
        id="get_player_achievements",
    ),
]

APP_ID_CALLS = [
    pytest.param(
        lambda steam, app_id: steam.games.get_player_achievements(STEAMID, app_id),
        ACHIEVEMENTS_PATH,
        NO_ACHIEVEMENTS,
        id="get_player_achievements",
    ),
    pytest.param(
        lambda steam, app_id: steam.games.get_schema_for_game(app_id),
        SCHEMA_PATH,
        TF2_SCHEMA_STUB,
        id="get_schema_for_game",
    ),
    pytest.param(
        lambda steam, app_id: steam.games.get_app_details(app_id),
        APP_DETAILS_PATH,
        UNKNOWN_APP_DETAILS,
        id="get_app_details",
    ),
]

INVALID_STEAMIDS = [
    pytest.param("", id="empty"),
    pytest.param("gabelogannewell", id="vanity-name"),
    pytest.param("STEAM_0:0:84901", id="steam2-format"),
    pytest.param(STEAMID[:-1], id="16-digits"),
    pytest.param("103582791429521412", id="group-steamid"),
]

INVALID_APP_IDS = [
    pytest.param(0, id="zero"),
    pytest.param(-440, id="negative"),
    pytest.param("440", id="numeric-string"),
    pytest.param(440.0, id="float"),
    pytest.param(None, id="none"),
]


# -- credentials and errors shared by every endpoint ---------------------------


@pytest.mark.parametrize(("call", "path", "reply"), KEYED_ENDPOINTS)
async def test_endpoint_sends_api_key_not_access_token(
    steam: Steam, fake_steam: FakeSteam, call: Call, path: str, reply: dict[str, Any]
) -> None:
    fake_steam.add("GET", path, json=reply)

    await call(steam)

    assert len(fake_steam.requests) == 1
    assert_sent_with_api_key(fake_steam.last, path)


@pytest.mark.parametrize(("call", "path", "reply"), ENDPOINTS)
async def test_http_error_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, call: Call, path: str, reply: dict[str, Any]
) -> None:
    fake_steam.add("GET", path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await call(steam)

    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    # MAX_RETRIES is 0: exactly one request, and the token never goes out.
    assert [r.path for r in fake_steam.requests] == [path]
    assert "access_token" not in fake_steam.last.query


@pytest.mark.parametrize("bad_id", INVALID_STEAMIDS)
@pytest.mark.parametrize(("call", "path", "reply"), STEAMID_CALLS)
async def test_invalid_steamid_is_rejected_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, str], Awaitable[object]],
    path: str,
    reply: dict[str, Any],
    bad_id: str,
) -> None:
    fake_steam.add("GET", path, json=reply)

    with pytest.raises(InvalidSteamIDError) as excinfo:
        await call(steam, bad_id)

    assert excinfo.value.steamid == bad_id
    assert fake_steam.requests == []


@pytest.mark.parametrize("bad_id", INVALID_APP_IDS)
@pytest.mark.parametrize(("call", "path", "reply"), APP_ID_CALLS)
async def test_invalid_app_id_is_rejected_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, Any], Awaitable[object]],
    path: str,
    reply: dict[str, Any],
    bad_id: Any,
) -> None:
    fake_steam.add("GET", path, json=reply)

    with pytest.raises(InvalidAppIDError) as excinfo:
        await call(steam, bad_id)

    assert excinfo.value.app_id == str(bad_id)
    assert fake_steam.requests == []


@pytest.mark.xfail(
    reason="#23: bool passes the app id check and is sent as appid=True",
    raises=pytest.fail.Exception,
)
async def test_bool_app_id_is_rejected_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SCHEMA_PATH, json=TF2_SCHEMA_STUB)

    with pytest.raises(InvalidAppIDError):
        await steam.games.get_schema_for_game(True)

    assert fake_steam.requests == []


# -- IPlayerService/GetOwnedGames ----------------------------------------------


async def test_get_owned_games_sends_steamid_and_default_flags(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=NO_GAMES)

    await steam.games.get_owned_games(STEAMID)

    assert_sent_with_api_key(fake_steam.last, OWNED_GAMES_PATH)
    assert fake_steam.last.params == {
        "steamid": STEAMID,
        "include_appinfo": "1",
        "include_played_free_games": "0",
        "key": API_KEY,
    }


@pytest.mark.parametrize(
    ("include_appinfo", "include_played_free_games", "expected"),
    [
        pytest.param(True, True, ("1", "1"), id="both"),
        pytest.param(False, True, ("0", "1"), id="free-games-only"),
        pytest.param(False, False, ("0", "0"), id="neither"),
    ],
)
async def test_get_owned_games_sends_flags_as_1_or_0(
    steam: Steam,
    fake_steam: FakeSteam,
    include_appinfo: bool,
    include_played_free_games: bool,
    expected: tuple[str, str],
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=NO_GAMES)

    await steam.games.get_owned_games(
        STEAMID,
        include_appinfo=include_appinfo,
        include_played_free_games=include_played_free_games,
    )

    query = fake_steam.last.query
    assert (
        query.getall("include_appinfo")[0],
        query.getall("include_played_free_games")[0],
    ) == expected


async def test_get_owned_games_omits_appids_filter_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=NO_GAMES)

    await steam.games.get_owned_games(STEAMID)

    assert not any(name.startswith("appids_filter") for name in fake_steam.last.query)


async def test_get_owned_games_sends_appids_filter_as_indexed_params(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        OWNED_GAMES_PATH,
        json={
            "response": {
                "game_count": 2,
                "games": [owned_game(440), owned_game(620)],
            }
        },
    )

    await steam.games.get_owned_games(STEAMID, appids_filter=[440, 620])

    query = fake_steam.last.query
    assert query.getall("appids_filter[0]", []) == ["440"]
    assert query.getall("appids_filter[1]", []) == ["620"]
    assert "appids_filter" not in query


async def test_get_owned_games_parses_games_with_appinfo(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=load_fixture("game_owned_games.json"))

    games = await steam.games.get_owned_games(STEAMID)

    assert all(isinstance(game, OwnedGame) for game in games)
    assert [(g.appid, g.name) for g in games] == [
        (220, "Half-Life 2"),
        (440, "Team Fortress 2"),
        (620, "Portal 2"),
    ]
    tf2 = games[1]
    assert tf2.playtime_forever == 48213
    assert tf2.playtime_2weeks == 95
    assert tf2.playtime_windows_forever == 47025
    assert tf2.playtime_mac_forever == 0
    assert tf2.playtime_linux_forever == 1093
    assert tf2.img_icon_url == "e3f595a92552da3d664ad00277fad2107345f743"


async def test_get_owned_games_playtime_helpers(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=load_fixture("game_owned_games.json"))

    hl2, tf2, portal2 = await steam.games.get_owned_games(STEAMID)

    assert tf2.playtime_hours == 803.5
    assert tf2.playtime_2weeks_hours == 1.6
    assert hl2.playtime_2weeks is None
    assert hl2.playtime_2weeks_hours is None
    assert portal2.playtime_hours == 0.0


async def test_get_owned_games_builds_icon_url_from_appid_and_hash(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=load_fixture("game_owned_games.json"))

    hl2 = (await steam.games.get_owned_games(STEAMID))[0]

    assert hl2.icon_url is not None
    assert hl2.icon_url.endswith(
        "media.steampowered.com/steamcommunity/public/images/apps/220/"
        "fcfb366051782b8ebf2aa297f3b746395858cb62.jpg"
    )
    assert hl2.icon_url.startswith("https://")


async def test_get_owned_games_parses_entries_without_appinfo(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        OWNED_GAMES_PATH,
        json={
            "response": {
                "game_count": 2,
                "games": [
                    owned_game(220, playtime_forever=1311),
                    owned_game(440, playtime_forever=48213, playtime_2weeks=95),
                ],
            }
        },
    )

    games = await steam.games.get_owned_games(STEAMID, include_appinfo=False)

    assert [(g.appid, g.name, g.playtime_forever) for g in games] == [
        (220, None, 1311),
        (440, None, 48213),
    ]
    assert games[0].icon_url is None


async def test_get_owned_games_public_profile_without_games_returns_empty_list(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=NO_GAMES)

    assert await steam.games.get_owned_games(STEAMID) == []


async def test_get_owned_games_empty_response_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # What GetOwnedGames answers when the game details are not public.
    fake_steam.api("GET", OWNED_GAMES_PATH, json={"response": {}})

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.games.get_owned_games(STEAMID)

    assert excinfo.value.steamid == STEAMID
    assert excinfo.value.status_code == 403


@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param({}, "Invalid response structure", id="no-response"),
        pytest.param(
            {"response": {"game_count": 1, "games": [{"name": "Half-Life 2"}]}},
            "Failed to get owned games",
            id="game-without-appid",
        ),
    ],
)
async def test_get_owned_games_unexpected_body_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any], message: str
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=body)

    with pytest.raises(SteamAPIError, match=message) as excinfo:
        await steam.games.get_owned_games(STEAMID)

    assert not isinstance(excinfo.value, PrivateProfileError)


# -- ISteamUserStats/GetPlayerAchievements -------------------------------------


async def test_get_player_achievements_sends_steamid_appid_and_language(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ACHIEVEMENTS_PATH, json=NO_ACHIEVEMENTS)

    await steam.games.get_player_achievements(STEAMID, 220)

    assert_sent_with_api_key(fake_steam.last, ACHIEVEMENTS_PATH)
    assert fake_steam.last.params == {
        "steamid": STEAMID,
        "appid": "220",
        "l": "english",
        "key": API_KEY,
    }


async def test_get_player_achievements_passes_language_through(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ACHIEVEMENTS_PATH, json=NO_ACHIEVEMENTS)

    await steam.games.get_player_achievements(STEAMID, 220, language="german")

    assert fake_steam.last.query.getall("l") == ["german"]


async def test_get_player_achievements_parses_achievements(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", ACHIEVEMENTS_PATH, json=load_fixture("game_player_achievements_440.json")
    )

    achievements = await steam.games.get_player_achievements(STEAMID, 440)

    assert [(a.apiname, a.achieved, a.unlocktime) for a in achievements] == [
        ("TF_PLAY_GAME_EVERYCLASS", 1, 1206047153),
        ("TF_PLAY_GAME_EVERYMAP", 1, 1206133580),
        ("TF_GET_HEALPOINTS", 0, 0),
    ]
    assert achievements[0].name == "Head of the Class"
    assert achievements[0].description == "Play a complete round with every class."


async def test_get_player_achievements_unlock_helpers(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", ACHIEVEMENTS_PATH, json=load_fixture("game_player_achievements_440.json")
    )

    unlocked, _, locked = await steam.games.get_player_achievements(STEAMID, 440)

    assert unlocked.is_achieved is True
    assert unlocked.unlock_date == datetime.fromtimestamp(1206047153)
    assert locked.is_achieved is False
    assert locked.unlock_date is None


async def test_get_player_achievements_game_without_achievements_returns_empty_list(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Steam leaves out "achievements" when the game has none.
    fake_steam.api("GET", ACHIEVEMENTS_PATH, json=NO_ACHIEVEMENTS)

    assert await steam.games.get_player_achievements(STEAMID, 220) == []


async def test_get_player_achievements_unrecognised_error_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # An error the library has no specific exception for. ("Requested app has
    # no stats" is not used here: it becomes GameNotFoundError, tested below.)
    fake_steam.api(
        "GET",
        ACHIEVEMENTS_PATH,
        json={"playerstats": {"error": "Internal error", "success": False}},
    )

    with pytest.raises(SteamAPIError, match="Internal error") as excinfo:
        await steam.games.get_player_achievements(STEAMID, 220)

    assert type(excinfo.value) is SteamAPIError


async def test_get_player_achievements_without_playerstats_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", ACHIEVEMENTS_PATH, json={})

    with pytest.raises(SteamAPIError, match="Invalid response structure"):
        await steam.games.get_player_achievements(STEAMID, 440)


@pytest.mark.parametrize(
    "status",
    [
        pytest.param(
            200,
            id="http-200",
        ),
        pytest.param(
            403,
            id="http-403-as-steam-sends-it",
        ),
    ],
)
async def test_get_player_achievements_private_profile_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam, status: int
) -> None:
    fake_steam.api(
        "GET",
        ACHIEVEMENTS_PATH,
        status=status,
        json={"playerstats": {"error": "Profile is not public", "success": False}},
    )

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.games.get_player_achievements(STEAMID, 440)

    assert excinfo.value.steamid == STEAMID


async def test_get_player_achievements_app_without_stats_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # What Steam answers for an app id with no stats (or no such app).
    fake_steam.api(
        "GET",
        ACHIEVEMENTS_PATH,
        status=400,
        json={"playerstats": {"error": "Requested app has no stats", "success": False}},
    )

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.games.get_player_achievements(STEAMID, 999999)

    assert excinfo.value.app_id == "999999"


# -- ISteamUserStats/GetSchemaForGame ------------------------------------------


async def test_get_schema_for_game_sends_appid_and_language(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SCHEMA_PATH, json=TF2_SCHEMA_STUB)

    await steam.games.get_schema_for_game(440, language="french")

    assert_sent_with_api_key(fake_steam.last, SCHEMA_PATH)
    assert fake_steam.last.params == {"appid": "440", "l": "french", "key": API_KEY}


async def test_get_schema_for_game_parses_schema(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SCHEMA_PATH, json=load_fixture("game_schema_440.json"))

    schema = await steam.games.get_schema_for_game(440)

    assert schema.gameName == "Team Fortress 2"
    assert schema.gameVersion == "142"
    assert schema.availableGameStats is not None
    assert [a["name"] for a in schema.availableGameStats["achievements"]] == [
        "TF_PLAY_GAME_EVERYCLASS",
        "TF_GET_HEALPOINTS",
    ]
    assert [s["name"] for s in schema.availableGameStats["stats"]] == [
        "Scout.accum.iNumberOfKills",
        "Medic.accum.iHealthPointsHealed",
    ]


async def test_get_schema_for_game_without_stats_section(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SCHEMA_PATH, json=TF2_SCHEMA_STUB)

    schema = await steam.games.get_schema_for_game(440)

    assert schema.availableGameStats is None


async def test_get_schema_for_game_without_game_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SCHEMA_PATH, json={})

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.games.get_schema_for_game(999999)

    assert excinfo.value.app_id == "999999"
    assert excinfo.value.status_code == 404


async def test_get_schema_for_game_empty_game_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # What Steam answers for an app id without a stats schema.
    fake_steam.api("GET", SCHEMA_PATH, json={"game": {}})

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.games.get_schema_for_game(999999)

    assert excinfo.value.app_id == "999999"


# -- store.steampowered.com/api/appdetails -------------------------------------


async def test_get_app_details_calls_store_without_credentials(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store(
        "GET", "/appdetails", json=load_fixture("game_appdetails_620.json")
    )

    await steam.games.get_app_details(620)

    request = fake_steam.last
    assert request.method == "GET"
    assert request.path == APP_DETAILS_PATH
    assert request.params == {"appids": "620", "cc": "US", "l": "english"}
    assert "Authorization" not in request.headers


async def test_get_app_details_needs_no_api_key(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    fake_steam.store(
        "GET", "/appdetails", json=load_fixture("game_appdetails_620.json")
    )

    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as token_only:
        details = await token_only.games.get_app_details(620)

    assert details is not None
    assert details.steam_appid == 620
    assert fake_steam.last.params == {"appids": "620", "cc": "US", "l": "english"}


async def test_get_app_details_passes_country_and_language_through(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store(
        "GET", "/appdetails", json=load_fixture("game_appdetails_620.json")
    )

    await steam.games.get_app_details(620, country="DE", language="german")

    assert fake_steam.last.params == {"appids": "620", "cc": "DE", "l": "german"}


async def test_get_app_details_parses_store_data(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store(
        "GET", "/appdetails", json=load_fixture("game_appdetails_620.json")
    )

    details = await steam.games.get_app_details(620)

    assert details is not None
    assert details.steam_appid == 620
    assert details.name == "Portal 2"
    assert details.type == "game"
    assert details.is_free is False
    assert details.required_age == 0
    assert details.developers == ["Valve"]
    assert details.publishers == ["Valve"]
    assert details.website == "http://www.thinkwithportals.com/"
    assert details.price_overview is not None
    assert details.price_overview["final_formatted"] == "$9.99"
    assert [g["description"] for g in details.genres] == ["Action", "Adventure"]
    assert details.header_image.startswith(
        "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/620/"
    )


async def test_get_app_details_release_and_platform_helpers(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store(
        "GET", "/appdetails", json=load_fixture("game_appdetails_620.json")
    )

    details = await steam.games.get_app_details(620)

    assert details is not None
    assert details.is_released is True
    assert details.platform_list == ["windows", "linux"]


async def test_get_app_details_coming_soon_is_not_released(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = load_fixture("game_appdetails_620.json")
    body["620"]["data"]["release_date"] = {"coming_soon": True, "date": "Coming soon"}
    fake_steam.store("GET", "/appdetails", json=body)

    details = await steam.games.get_app_details(620)

    assert details is not None
    assert details.is_released is False


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"9999999": {"success": False}}, id="success-false"),
        pytest.param({}, id="app-missing"),
    ],
)
async def test_get_app_details_unknown_app_returns_none(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.store("GET", "/appdetails", json=body)

    assert await steam.games.get_app_details(9999999) is None


async def test_get_app_details_null_body_returns_none(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store("GET", "/appdetails", text="null", content_type="application/json")

    assert await steam.games.get_app_details(9999999) is None


async def test_get_app_details_invalid_data_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.store(
        "GET",
        "/appdetails",
        json={"620": {"success": True, "data": {"name": "Portal 2"}}},
    )

    with pytest.raises(SteamAPIError, match="Failed to get app details"):
        await steam.games.get_app_details(620)


# -- IStoreService/GetAppList (#13) ---------------------------------------------


def app_list_page(
    apps: list[dict[str, Any]], last_appid: int | None = None
) -> dict[str, Any]:
    """A GetAppList page; ``last_appid`` set means another page follows."""
    page: dict[str, Any] = {"apps": apps}
    if last_appid is not None:
        page.update(have_more_results=True, last_appid=last_appid)
    return {"response": page}


async def test_get_app_list_uses_store_service(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=STORE_APP_LIST)

    apps = await steam.games.get_app_list()

    assert [r.path for r in fake_steam.requests] == [STORE_APP_LIST_PATH]
    assert_sent_with_api_key(fake_steam.last, STORE_APP_LIST_PATH)
    assert [(app.appid, app.name) for app in apps] == EXPECTED_APPS


async def test_get_app_list_parses_apps(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=STORE_APP_LIST)

    apps = await steam.games.get_app_list()

    assert all(isinstance(app, SteamApp) for app in apps)
    assert apps[-1] == SteamApp(
        appid=730,
        name="Counter-Strike 2",
        last_modified=1759184524,
        price_change_number=31125813,
    )


async def test_get_app_list_asks_for_every_app_type_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=STORE_APP_LIST)

    await steam.games.get_app_list()

    assert json.loads(fake_steam.last.params["input_json"]) == {
        "last_appid": 0,
        "max_results": 10000,
        "include_games": True,
        "include_dlc": True,
        "include_software": True,
        "include_videos": True,
        "include_hardware": True,
    }


async def test_get_app_list_follows_pages(steam: Steam, fake_steam: FakeSteam) -> None:
    apps = STORE_APP_LIST["response"]["apps"]
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=app_list_page(apps[:2], 400))
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=app_list_page(apps[2:]))

    result = await steam.games.get_app_list(max_results=2)

    assert [(app.appid, app.name) for app in result] == EXPECTED_APPS
    sent = [json.loads(r.params["input_json"]) for r in fake_steam.requests]
    assert [(s["last_appid"], s["max_results"]) for s in sent] == [(0, 2), (400, 2)]


async def test_get_app_list_stops_on_a_page_that_does_not_advance(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    apps = STORE_APP_LIST["response"]["apps"][:2]
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=app_list_page(apps, 400))

    with pytest.raises(SteamAPIError, match="same app list page"):
        await steam.games.get_app_list()

    assert len(fake_steam.requests) == 2


async def test_get_app_list_page_passes_filters(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=app_list_page([], None))

    page = await steam.games.get_app_list_page(
        last_appid=730,
        max_results=50_000,
        include_dlc=False,
        if_modified_since=1759000000,
        have_description_language="english",
    )

    assert page.apps == []
    assert page.have_more_results is False
    sent = json.loads(fake_steam.last.params["input_json"])
    assert sent["last_appid"] == 730
    assert sent["max_results"] == 50_000
    assert sent["include_dlc"] is False
    assert sent["include_games"] is True
    assert sent["if_modified_since"] == 1759000000
    assert sent["have_description_language"] == "english"


async def test_iter_app_list_yields_apps_page_by_page(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    apps = STORE_APP_LIST["response"]["apps"]
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=app_list_page(apps[:2], 400))
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=app_list_page(apps[2:]))

    seen = []
    async for app in steam.games.iter_app_list(max_results=2):
        seen.append(app.appid)
        if app.appid == 400:
            assert len(fake_steam.requests) == 1

    assert seen == [10, 400, 620, 730]


async def test_get_app_list_without_response_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STORE_APP_LIST_PATH, json={})

    with pytest.raises(SteamAPIError, match="Invalid response structure"):
        await steam.games.get_app_list()


# -- search_games --------------------------------------------------------------


async def test_search_games_within_owned_games_makes_no_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    owned = [
        OwnedGame(appid=400, name="Portal", playtime_forever=0),
        OwnedGame(appid=620, name="Portal 2", playtime_forever=0),
        OwnedGame(appid=440, name="Team Fortress 2", playtime_forever=0),
        OwnedGame(appid=4000, playtime_forever=0),
    ]

    results = await steam.games.search_games("  PORTAL ", owned_games=owned)

    assert results == [
        SteamApp(appid=400, name="Portal"),
        SteamApp(appid=620, name="Portal 2"),
    ]
    assert fake_steam.requests == []


async def test_search_games_without_owned_games_searches_the_app_list(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=STORE_APP_LIST)

    results = await steam.games.search_games("counter-strike")

    assert [(app.appid, app.name) for app in results] == [
        (10, "Counter-Strike"),
        (730, "Counter-Strike 2"),
    ]


async def test_search_games_with_empty_owned_games_makes_no_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", STORE_APP_LIST_PATH, json=STORE_APP_LIST)

    results = await steam.games.search_games("portal", owned_games=[])

    assert results == []
    assert fake_steam.requests == []


async def test_get_owned_games_sends_optional_params_only_when_set(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=NO_GAMES)

    await steam.games.get_owned_games(
        STEAMID,
        include_extended_appinfo=True,
        include_free_sub=True,
        skip_unvetted_apps=False,
        include_family_licenses=True,
        language="german",
    )

    params = fake_steam.last.params
    assert params["include_extended_appinfo"] == "1"
    assert params["include_free_sub"] == "1"
    assert params["skip_unvetted_apps"] == "0"
    assert params["include_family_licenses"] == "1"
    assert params["language"] == "german"


async def test_get_owned_games_parses_extended_fields(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", OWNED_GAMES_PATH, json=load_fixture("game_owned_games.json"))

    hl2, tf2, _ = await steam.games.get_owned_games(STEAMID)

    assert hl2.has_community_visible_stats is True
    assert hl2.content_descriptorids == [2, 5]
    assert hl2.playtime_disconnected == 0
    assert tf2.playtime_deck_forever == 95
    assert tf2.rtime_last_played == 1727910021
    assert tf2.last_played == datetime.fromtimestamp(1727910021)


async def test_get_app_details_parses_optional_fields(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    body = load_fixture("game_appdetails_620.json")
    body["620"]["data"]["linux_requirements"] = []
    fake_steam.store("GET", "/appdetails", json=body)

    details = await steam.games.get_app_details(620)

    assert details is not None
    assert details.dlc == [323180]
    assert details.packages == [7877, 204343]
    assert details.achievements == {"total": 51}
    assert isinstance(details.pc_requirements, dict)
    assert details.linux_requirements == []


async def test_schema_achievement_without_description() -> None:
    from steamy_py.models.game import SchemaAchievement

    achievement = SchemaAchievement(
        name="SECRET",
        displayName="Secret",
        icon="https://example.invalid/a.jpg",
        icongray="https://example.invalid/b.jpg",
        hidden=1,
    )

    assert achievement.description is None
    assert achievement.is_hidden
