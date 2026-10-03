"""Tests for ``steam.stats``: player counts, user and global statistics, and the
IPlayerService achievement methods."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    GameNotFoundError,
    InvalidAppIDError,
    InvalidSteamIDError,
    NewsItem,
    PlayerCount,
    PrivateProfileError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
    SteamID,
    UserStat,
)
from steamy_py.models.stats import (
    AchievementProgress,
    EAchievementProgressType,
    GameAchievement,
    GameAchievements,
    GlobalAchievementStat,
    GlobalStat,
    TopAchievement,
    TopAchievementsGame,
    UserAchievement,
)
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

CURRENT_PLAYERS_PATH = "/ISteamUserStats/GetNumberOfCurrentPlayers/v1/"
NEWS_PATH = "/ISteamNews/GetNewsForApp/v2/"
USER_STATS_PATH = "/ISteamUserStats/GetUserStatsForGame/v2/"
GLOBAL_ACHIEVEMENTS_PATH = "/ISteamUserStats/GetGlobalAchievementPercentagesForApp/v2/"
GLOBAL_STATS_PATH = "/ISteamUserStats/GetGlobalStatsForGame/v1/"
PLAYER_ACHIEVEMENTS_PATH = "/ISteamUserStats/GetPlayerAchievements/v1/"

CS2_PLAYERS: dict[str, Any] = {"response": {"player_count": 1043578, "result": 1}}
NO_NEWS: dict[str, Any] = {"appnews": {"appid": 440, "newsitems": [], "count": 0}}
CS2_NO_STATS: dict[str, Any] = {
    "playerstats": {"steamID": STEAMID, "gameName": "ValveTestApp260"}
}

# Real GetGlobalAchievementPercentagesForApp/v2 body: percentages are strings.
TF2_ACHIEVEMENT_PERCENTAGES: dict[str, Any] = {
    "achievementpercentages": {
        "achievements": [
            {"name": "TF_PLAY_GAME_EVERYCLASS", "percent": "71.9"},
            {"name": "TF_GET_HEALPOINTS", "percent": "23.4"},
            {"name": "TF_KILL_NEMESIS", "percent": "0.5"},
        ]
    }
}

# Real GetGlobalStatsForGame/v1 body: each stat is an object, totals are strings.
TF2_GLOBAL_STATS: dict[str, Any] = {
    "response": {
        "globalstats": {
            "global.map.emp_isle": {"total": "2346826"},
            "global.map.emp_mainland": {"total": "123"},
        },
        "result": 1,
    }
}
TF2_STAT_NAMES = ["global.map.emp_isle", "global.map.emp_mainland"]

Call = Callable[[Steam], Awaitable[object]]


def sent_params(request: RecordedRequest) -> dict[str, str]:
    """Query parameters of ``request`` other than the credentials."""
    return {
        name: value
        for name, value in request.params.items()
        if name not in {"key", "access_token"}
    }


# Every method, with the path it calls.
ENDPOINTS = [
    pytest.param(
        lambda steam: steam.stats.get_current_players(730),
        CURRENT_PLAYERS_PATH,
        id="get_current_players",
    ),
    pytest.param(
        lambda steam: steam.store.get_news_for_app(440),
        NEWS_PATH,
        id="get_news_for_app",
    ),
    pytest.param(
        lambda steam: steam.stats.get_user_stats_for_game(STEAMID, 730),
        USER_STATS_PATH,
        id="get_user_stats_for_game",
    ),
    pytest.param(
        lambda steam: steam.stats.get_user_achievements_only(STEAMID, 730),
        PLAYER_ACHIEVEMENTS_PATH,
        id="get_user_achievements_only",
    ),
    pytest.param(
        lambda steam: steam.stats.get_user_stats_only(STEAMID, 730),
        USER_STATS_PATH,
        id="get_user_stats_only",
    ),
    pytest.param(
        lambda steam: steam.stats.get_global_achievement_percentages(440),
        GLOBAL_ACHIEVEMENTS_PATH,
        id="get_global_achievement_percentages",
    ),
    pytest.param(
        lambda steam: steam.stats.get_global_stats_for_game(440, TF2_STAT_NAMES),
        GLOBAL_STATS_PATH,
        id="get_global_stats_for_game",
    ),
]

STEAMID_CALLS = [
    pytest.param(
        lambda steam, steamid: steam.stats.get_user_stats_for_game(steamid, 730),
        id="get_user_stats_for_game",
    ),
    pytest.param(
        lambda steam, steamid: steam.stats.get_user_achievements_only(steamid, 730),
        id="get_user_achievements_only",
    ),
    pytest.param(
        lambda steam, steamid: steam.stats.get_user_stats_only(steamid, 730),
        id="get_user_stats_only",
    ),
]

APP_ID_CALLS = [
    pytest.param(
        lambda steam, app_id: steam.stats.get_current_players(app_id),
        id="get_current_players",
    ),
    pytest.param(
        lambda steam, app_id: steam.store.get_news_for_app(app_id),
        id="get_news_for_app",
    ),
    pytest.param(
        lambda steam, app_id: steam.stats.get_user_stats_for_game(STEAMID, app_id),
        id="get_user_stats_for_game",
    ),
    pytest.param(
        lambda steam, app_id: steam.stats.get_user_achievements_only(STEAMID, app_id),
        id="get_user_achievements_only",
    ),
    pytest.param(
        lambda steam, app_id: steam.stats.get_user_stats_only(STEAMID, app_id),
        id="get_user_stats_only",
    ),
    pytest.param(
        lambda steam, app_id: steam.stats.get_global_achievement_percentages(app_id),
        id="get_global_achievement_percentages",
    ),
    pytest.param(
        lambda steam, app_id: steam.stats.get_global_stats_for_game(
            app_id, TF2_STAT_NAMES
        ),
        id="get_global_stats_for_game",
    ),
]

INVALID_STEAMIDS = [
    pytest.param("", id="empty"),
    pytest.param("gabelogannewell", id="vanity-name"),
    pytest.param("[U:1:169802]", id="steam3-format"),
    pytest.param(STEAMID + "0", id="18-digits"),
    pytest.param("103582791429521412", id="group-steamid"),
]

INVALID_APP_IDS = [
    pytest.param(0, id="zero"),
    pytest.param(-730, id="negative"),
    pytest.param("730", id="numeric-string"),
    pytest.param(730.0, id="float"),
    pytest.param(None, id="none"),
]


# -- credentials ---------------------------------------------------------------

KEYLESS_ENDPOINTS = [
    pytest.param(
        lambda steam: steam.stats.get_current_players(730),
        CURRENT_PLAYERS_PATH,
        CS2_PLAYERS,
        id="get_current_players",
    ),
    pytest.param(
        lambda steam: steam.store.get_news_for_app(440),
        NEWS_PATH,
        {"appnews": {"appid": 440, "newsitems": [], "count": 0}},
        id="get_news_for_app",
    ),
    pytest.param(
        lambda steam: steam.stats.get_global_achievement_percentages(440),
        GLOBAL_ACHIEVEMENTS_PATH,
        {"achievementpercentages": {"achievements": []}},
        id="get_global_achievement_percentages",
    ),
    pytest.param(
        lambda steam: steam.stats.get_global_stats_for_game(440, TF2_STAT_NAMES),
        GLOBAL_STATS_PATH,
        {"response": {"result": 1, "globalstats": {}}},
        id="get_global_stats_for_game",
    ),
]


@pytest.mark.parametrize(("call", "path", "reply"), KEYLESS_ENDPOINTS)
async def test_keyless_endpoint_sends_no_credential(
    steam: Steam, fake_steam: FakeSteam, call: Call, path: str, reply: Any
) -> None:
    fake_steam.api("GET", path, json=reply)

    await call(steam)

    assert "key" not in fake_steam.last.query
    assert "access_token" not in fake_steam.last.query


@pytest.mark.parametrize(("call", "path", "reply"), KEYLESS_ENDPOINTS)
async def test_keyless_endpoint_works_without_credentials(
    fake_steam: FakeSteam, settings: Settings, call: Call, path: str, reply: Any
) -> None:
    fake_steam.api("GET", path, json=reply)

    async with Steam(settings=settings) as steam:
        await call(steam)

    assert len(fake_steam.requests) == 1


# -- errors and validation shared by every endpoint ----------------------------


@pytest.mark.parametrize(("call", "path"), ENDPOINTS)
async def test_http_error_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, call: Call, path: str
) -> None:
    fake_steam.api("GET", path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await call(steam)

    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    assert [r.path for r in fake_steam.requests] == [path]
    # None of these Web API calls takes the user's access token.
    assert "access_token" not in fake_steam.last.query


@pytest.mark.parametrize("bad_id", INVALID_STEAMIDS)
@pytest.mark.parametrize("call", STEAMID_CALLS)
async def test_invalid_steamid_is_rejected_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, str], Awaitable[object]],
    bad_id: str,
) -> None:
    fake_steam.api("GET", USER_STATS_PATH, json=CS2_NO_STATS)

    with pytest.raises(InvalidSteamIDError) as excinfo:
        await call(steam, bad_id)

    assert excinfo.value.steamid == bad_id
    assert fake_steam.requests == []


@pytest.mark.parametrize("bad_id", INVALID_APP_IDS)
@pytest.mark.parametrize("call", APP_ID_CALLS)
async def test_invalid_app_id_is_rejected_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, Any], Awaitable[object]],
    bad_id: Any,
) -> None:
    with pytest.raises(InvalidAppIDError) as excinfo:
        await call(steam, bad_id)

    assert excinfo.value.app_id == str(bad_id)
    assert fake_steam.requests == []


async def test_bool_app_id_is_rejected_before_any_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", CURRENT_PLAYERS_PATH, json=CS2_PLAYERS)

    with pytest.raises(InvalidAppIDError):
        await steam.stats.get_current_players(True)

    assert fake_steam.requests == []


# -- ISteamUserStats/GetNumberOfCurrentPlayers ---------------------------------


async def test_get_current_players_sends_appid(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", CURRENT_PLAYERS_PATH, json=CS2_PLAYERS)

    await steam.stats.get_current_players(730)

    assert fake_steam.last.method == "GET"
    assert fake_steam.last.path == CURRENT_PLAYERS_PATH
    assert sent_params(fake_steam.last) == {"appid": "730"}
    assert "access_token" not in fake_steam.last.query


async def test_get_current_players_parses_player_count(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", CURRENT_PLAYERS_PATH, json=CS2_PLAYERS)

    count = await steam.stats.get_current_players(730)

    assert isinstance(count, PlayerCount)
    assert count.player_count == 1043578
    assert count.result == 1
    assert count.is_success is True


async def test_get_current_players_accepts_zero_players(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", CURRENT_PLAYERS_PATH, json={"response": {"player_count": 0, "result": 1}}
    )

    count = await steam.stats.get_current_players(70)

    assert count.player_count == 0


async def test_get_current_players_without_response_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", CURRENT_PLAYERS_PATH, json={})

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.stats.get_current_players(999999)

    assert excinfo.value.app_id == "999999"


async def test_get_current_players_unknown_app_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Steam leaves out player_count for an app it does not know.
    fake_steam.api("GET", CURRENT_PLAYERS_PATH, json={"response": {"result": 42}})

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.stats.get_current_players(999999)

    assert excinfo.value.app_id == "999999"


async def test_get_current_players_works_with_only_an_access_token(
    fake_steam: FakeSteam, settings: Settings
) -> None:
    fake_steam.api("GET", CURRENT_PLAYERS_PATH, json=CS2_PLAYERS)

    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as steam:
        count = await steam.stats.get_current_players(730)

    assert count.player_count == 1043578
    assert sent_params(fake_steam.last) == {"appid": "730"}
    assert "key" not in fake_steam.last.query


# -- ISteamNews/GetNewsForApp --------------------------------------------------


async def test_get_news_for_app_sends_default_count_and_length(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NO_NEWS)

    await steam.store.get_news_for_app(440)

    assert fake_steam.last.method == "GET"
    assert fake_steam.last.path == NEWS_PATH
    assert sent_params(fake_steam.last) == {
        "appid": "440",
        "count": "20",
        "maxlength": "300",
    }


@pytest.mark.parametrize(
    ("count", "max_length", "expected"),
    [
        pytest.param(5, 300, {"count": "5", "maxlength": "300"}, id="fewer-items"),
        pytest.param(20, 0, {"count": "20", "maxlength": "0"}, id="full-contents"),
        pytest.param(
            50,
            300,
            {"count": "50", "maxlength": "300"},
            id="more-than-20",
        ),
    ],
)
async def test_get_news_for_app_passes_count_and_length_through(
    steam: Steam,
    fake_steam: FakeSteam,
    count: int,
    max_length: int,
    expected: dict[str, str],
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NO_NEWS)

    await steam.store.get_news_for_app(440, count=count, max_length=max_length)

    assert sent_params(fake_steam.last) == {"appid": "440", **expected}


async def test_get_news_for_app_sends_paging_and_filters(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=NO_NEWS)

    await steam.store.get_news_for_app(
        440,
        end_date=1727740800,
        feeds=["tf2_blog", "steam_community_announcements"],
        tags=["patchnotes"],
    )

    assert sent_params(fake_steam.last) == {
        "appid": "440",
        "count": "20",
        "maxlength": "300",
        "enddate": "1727740800",
        "feeds": "tf2_blog,steam_community_announcements",
        "tags": "patchnotes",
    }


async def test_get_news_for_app_parses_news_items(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=load_fixture("stats_news_440.json"))

    news = await steam.store.get_news_for_app(440)

    assert all(isinstance(item, NewsItem) for item in news)
    blog, announcement = news
    assert blog.gid == "5765041530813586405"
    assert blog.title == "Team Fortress 2 Update Released"
    assert blog.url == (
        "https://steamstore-a.akamaihd.net/news/externalpost/tf2_blog/"
        "5765041530813586405"
    )
    assert blog.is_external_url is True
    assert blog.author == ""
    assert blog.feedlabel == "TF2 Blog"
    assert blog.feedname == "tf2_blog"
    assert blog.date == 1727301600
    assert blog.appid == 440
    assert announcement.author == "Erik"
    assert announcement.feedname == "steam_community_announcements"


async def test_get_news_for_app_news_item_helpers(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=load_fixture("stats_news_440.json"))

    blog, announcement = await steam.store.get_news_for_app(440)

    assert blog.is_official is False
    assert announcement.is_official is True
    assert blog.publish_date == datetime.fromtimestamp(1727301600)


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(NO_NEWS, id="no-items"),
        pytest.param({}, id="no-appnews"),
    ],
)
async def test_get_news_for_app_without_news_returns_empty_list(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.api("GET", NEWS_PATH, json=body)

    assert await steam.store.get_news_for_app(440) == []


async def test_get_news_for_app_malformed_item_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        NEWS_PATH,
        json={"appnews": {"appid": 440, "newsitems": [{"gid": "1"}], "count": 1}},
    )

    with pytest.raises(SteamAPIError, match="Failed to get news"):
        await steam.store.get_news_for_app(440)


# -- ISteamUserStats/GetUserStatsForGame ---------------------------------------


async def test_get_user_stats_for_game_sends_steamid_and_appid_with_key(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", USER_STATS_PATH, json=CS2_NO_STATS)

    await steam.stats.get_user_stats_for_game(STEAMID, 730)

    request = fake_steam.last
    assert request.method == "GET"
    assert request.path == USER_STATS_PATH
    assert request.params == {"steamid": STEAMID, "appid": "730", "key": API_KEY}
    assert "access_token" not in request.query


async def test_get_user_stats_for_game_parses_stats_and_achievements(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", USER_STATS_PATH, json=load_fixture("stats_user_stats_730.json")
    )

    result = await steam.stats.get_user_stats_for_game(STEAMID, 730)

    assert result.steamID == STEAMID
    assert result.gameName == "ValveTestApp260"
    assert [(s.name, s.value) for s in result.stats] == [
        ("total_kills", 18734),
        ("total_deaths", 16502),
        ("total_time_played", 1953262),
        ("total_kills_headshot", 8123),
    ]
    assert [(a.name, a.is_achieved) for a in result.achievements] == [
        ("WIN_BOMB_PLANT", True),
        ("BOMB_PLANT_LOW", True),
        ("KILL_ENEMY_LOW", True),
    ]


async def test_get_user_stats_for_game_keeps_float_stat_values(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        USER_STATS_PATH,
        json={
            "playerstats": {
                "steamID": STEAMID,
                "gameName": "Portal 2",
                "stats": [{"name": "fastest_run", "value": 312.25}],
            }
        },
    )

    result = await steam.stats.get_user_stats_for_game(STEAMID, 620)

    assert result.stats[0].value == 312.25
    assert result.achievements == []


async def test_get_user_stats_for_game_without_playerstats_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", USER_STATS_PATH, json={})

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.stats.get_user_stats_for_game(STEAMID, 999999)

    assert excinfo.value.app_id == "999999"


async def test_get_user_stats_for_game_unrecognised_error_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # An error the library has no specific exception for. ("Requested app has
    # no stats" is not used here: it should become GameNotFoundError, see below.)
    fake_steam.api(
        "GET",
        USER_STATS_PATH,
        json={"playerstats": {"error": "Internal error", "success": False}},
    )

    with pytest.raises(SteamAPIError, match="Internal error") as excinfo:
        await steam.stats.get_user_stats_for_game(STEAMID, 440)

    assert type(excinfo.value) is SteamAPIError


@pytest.mark.parametrize(
    ("status", "error", "expected"),
    [
        pytest.param(
            403,
            "Profile is not public",
            PrivateProfileError,
            id="private-profile-403",
        ),
        pytest.param(
            400,
            "Requested app has no stats",
            GameNotFoundError,
            id="app-without-stats-400",
        ),
    ],
)
async def test_get_user_stats_for_game_maps_steam_errors(
    steam: Steam,
    fake_steam: FakeSteam,
    status: int,
    error: str,
    expected: type[SteamAPIError],
) -> None:
    fake_steam.api(
        "GET",
        USER_STATS_PATH,
        status=status,
        json={"playerstats": {"error": error, "success": False}},
    )

    with pytest.raises(expected):
        await steam.stats.get_user_stats_for_game(STEAMID, 440)


async def test_get_user_achievements_only_returns_locked_and_unlocked(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        PLAYER_ACHIEVEMENTS_PATH,
        json=load_fixture("game_player_achievements_440.json"),
    )

    achievements = await steam.stats.get_user_achievements_only(STEAMID, 440)

    assert all(isinstance(a, UserAchievement) for a in achievements)
    assert [(a.name, a.is_achieved, a.unlocktime) for a in achievements] == [
        ("TF_PLAY_GAME_EVERYCLASS", True, 1206047153),
        ("TF_PLAY_GAME_EVERYMAP", True, 1206133580),
        ("TF_GET_HEALPOINTS", False, 0),
    ]
    assert fake_steam.requests_to(USER_STATS_PATH) == []
    assert fake_steam.last.params["appid"] == "440"


async def test_get_user_achievements_only_private_profile_raises(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        PLAYER_ACHIEVEMENTS_PATH,
        status=403,
        json={"playerstats": {"error": "Profile is not public", "success": False}},
    )

    with pytest.raises(PrivateProfileError):
        await steam.stats.get_user_achievements_only(STEAMID, 440)


async def test_get_user_stats_only_returns_stats(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", USER_STATS_PATH, json=load_fixture("stats_user_stats_730.json")
    )

    stats = await steam.stats.get_user_stats_only(STEAMID, 730)

    assert all(isinstance(s, UserStat) for s in stats)
    assert {s.name: s.value for s in stats}["total_kills"] == 18734
    assert len(fake_steam.requests_to(USER_STATS_PATH)) == 1


# -- ISteamUserStats/GetGlobalAchievementPercentagesForApp ---------------------


async def test_get_global_achievement_percentages_sends_gameid(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GLOBAL_ACHIEVEMENTS_PATH, json={})

    with pytest.raises(SteamAPIError):
        await steam.stats.get_global_achievement_percentages(440)

    assert fake_steam.last.method == "GET"
    assert fake_steam.last.path == GLOBAL_ACHIEVEMENTS_PATH
    assert sent_params(fake_steam.last) == {"gameid": "440"}


async def test_get_global_achievement_percentages_without_data_raises_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GLOBAL_ACHIEVEMENTS_PATH, json={})

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.stats.get_global_achievement_percentages(999999)

    assert excinfo.value.app_id == "999999"


async def test_get_global_achievement_percentages_parses_real_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GLOBAL_ACHIEVEMENTS_PATH, json=TF2_ACHIEVEMENT_PERCENTAGES)

    stats = await steam.stats.get_global_achievement_percentages(440)

    assert stats == [
        GlobalAchievementStat(name="TF_PLAY_GAME_EVERYCLASS", percent=71.9),
        GlobalAchievementStat(name="TF_GET_HEALPOINTS", percent=23.4),
        GlobalAchievementStat(name="TF_KILL_NEMESIS", percent=0.5),
    ]
    assert stats[0].completion_rate == pytest.approx(0.719)


# -- ISteamUserStats/GetGlobalStatsForGame -------------------------------------


async def test_get_global_stats_for_game_sends_indexed_names_and_dates(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GLOBAL_STATS_PATH, json={})

    with pytest.raises(SteamAPIError):
        await steam.stats.get_global_stats_for_game(
            440, TF2_STAT_NAMES, start_date=1727740800, end_date=1727827200
        )

    assert fake_steam.last.method == "GET"
    assert fake_steam.last.path == GLOBAL_STATS_PATH
    assert sent_params(fake_steam.last) == {
        "appid": "440",
        "count": "2",
        "name[0]": "global.map.emp_isle",
        "name[1]": "global.map.emp_mainland",
        "startdate": "1727740800",
        "enddate": "1727827200",
    }


async def test_get_global_stats_for_game_omits_dates_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GLOBAL_STATS_PATH, json={})

    with pytest.raises(SteamAPIError):
        await steam.stats.get_global_stats_for_game(440, ["global.map.emp_isle"])

    assert sent_params(fake_steam.last) == {
        "appid": "440",
        "count": "1",
        "name[0]": "global.map.emp_isle",
    }


async def test_get_global_stats_for_game_requires_a_stat_name(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GLOBAL_STATS_PATH, json=TF2_GLOBAL_STATS)

    with pytest.raises(ValueError, match="At least one stat name"):
        await steam.stats.get_global_stats_for_game(440, [])

    assert fake_steam.requests == []


async def test_get_global_stats_for_game_without_response_raises_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GLOBAL_STATS_PATH, json={})

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.stats.get_global_stats_for_game(999999, ["global.map.emp_isle"])

    assert excinfo.value.app_id == "999999"


async def test_get_global_stats_for_game_failed_lookup_raises_game_not_found(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # A failed lookup has a result other than 1 and no globalstats.
    fake_steam.api("GET", GLOBAL_STATS_PATH, json={"response": {"result": 8}})

    with pytest.raises(GameNotFoundError) as excinfo:
        await steam.stats.get_global_stats_for_game(999999, ["global.map.emp_isle"])

    assert excinfo.value.app_id == "999999"


async def test_get_global_stats_for_game_parses_real_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GLOBAL_STATS_PATH, json=TF2_GLOBAL_STATS)

    stats = await steam.stats.get_global_stats_for_game(440, TF2_STAT_NAMES)

    assert stats == [
        GlobalStat(name="global.map.emp_isle", total=2346826),
        GlobalStat(name="global.map.emp_mainland", total=123),
    ]


# -- IPlayerService achievement summaries ------------------------------------
#
# GetAchievementsProgress (POST) and GetTopAchievementsForGames (GET) send the
# API key when the client has one, else the access token; GetGameAchievements
# needs no credential and must send none.
#
# stats_get_top_achievements_for_games.json is a real reply published in
# Kiro85/Platinum's API docs (trimmed to the two achievements shown there).
# stats_get_game_achievements.json and stats_get_achievements_progress.json
# are built from CPlayer_GetGameAchievements_Response and
# CPlayer_GetAchievementsProgress_Response (SteamDatabase/Protobufs) with real
# TF2 names, descriptions and unlock rates from the other fixtures here; the
# percentage is a float32 written out the way Steam writes floats.

ACHIEVEMENTS_PROGRESS_PATH = "/IPlayerService/GetAchievementsProgress/v1/"
GAME_ACHIEVEMENTS_PATH = "/IPlayerService/GetGameAchievements/v1/"
TOP_ACHIEVEMENTS_PATH = "/IPlayerService/GetTopAchievementsForGames/v1/"

ACHIEVEMENTS_PROGRESS: dict[str, Any] = load_fixture(
    "stats_get_achievements_progress.json"
)
GAME_ACHIEVEMENTS: dict[str, Any] = load_fixture("stats_get_game_achievements.json")
TOP_ACHIEVEMENTS: dict[str, Any] = load_fixture(
    "stats_get_top_achievements_for_games.json"
)
EMPTY_RESPONSE: dict[str, Any] = {"response": {}}

INVALID_APP_ID_LISTS = [
    pytest.param(0, id="zero"),
    pytest.param(True, id="bool"),
    pytest.param("440", id="str"),
    pytest.param(b"440", id="bytes"),
    pytest.param(2**32, id="above-uint32"),
    pytest.param([440, 0], id="zero-in-list"),
    pytest.param([440, None], id="none-in-list"),
    pytest.param([440.0], id="float-in-list"),
]


@dataclass(frozen=True)
class AchievementEndpoint:
    """One achievement-summary method, called with realistic arguments."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    verb: str
    path: str
    reply: dict[str, Any]
    malformed: Any  # JSON that does not fit the method's model
    operation: str  # what the error message says failed

    def serve(self, fake_steam: FakeSteam, **reply: Any) -> None:
        """Register ``reply`` (default: the realistic one) for this method."""
        fake_steam.add(self.verb, self.path, **(reply or {"json": self.reply}))


ACHIEVEMENT_ENDPOINTS = [
    AchievementEndpoint(
        "get_achievements_progress",
        lambda steam: steam.stats.get_achievements_progress(STEAMID, [440, 620]),
        "POST",
        ACHIEVEMENTS_PROGRESS_PATH,
        ACHIEVEMENTS_PROGRESS,
        {"response": {"achievement_progress": [{"total": "many"}]}},
        "get achievements progress",
    ),
    AchievementEndpoint(
        "get_game_achievements",
        lambda steam: steam.stats.get_game_achievements(440),
        "GET",
        GAME_ACHIEVEMENTS_PATH,
        GAME_ACHIEVEMENTS,
        {"response": {"achievements": {"internal_name": "TF_GET_HEALPOINTS"}}},
        "get game achievements",
    ),
    AchievementEndpoint(
        "get_top_achievements_for_games",
        lambda steam: steam.stats.get_top_achievements_for_games(
            STEAMID, 1342330, max_achievements=2
        ),
        "GET",
        TOP_ACHIEVEMENTS_PATH,
        TOP_ACHIEVEMENTS,
        {"response": {"games": [{"achievements": [{"hidden": "maybe"}]}]}},
        "get top achievements for games",
    ),
]
KEY_OR_TOKEN_ENDPOINTS = [ACHIEVEMENT_ENDPOINTS[0], ACHIEVEMENT_ENDPOINTS[2]]


def achievement_endpoints(endpoints: list[AchievementEndpoint]) -> Any:
    return pytest.mark.parametrize(
        "endpoint", [pytest.param(endpoint, id=endpoint.name) for endpoint in endpoints]
    )


def sent_pairs(pairs: Any) -> dict[str, str]:
    """``pairs`` (a query string or form body) as a dict, checking that no
    name was sent twice."""
    items = list(pairs.items())
    assert len({name for name, _ in items}) == len(items), items
    return dict(items)


def credential_of(request: RecordedRequest) -> dict[str, str]:
    """The credentials ``request`` carried, in its query string or form."""
    return {
        name: value
        for pairs in (request.query, request.form)
        for name, value in pairs.items()
        if name in {"key", "access_token"}
    }


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


@achievement_endpoints(ACHIEVEMENT_ENDPOINTS)
async def test_achievement_method_is_one_request_with_documented_verb_and_path(
    steam: Steam, fake_steam: FakeSteam, endpoint: AchievementEndpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [
        (endpoint.verb, endpoint.path)
    ]


@achievement_endpoints(ACHIEVEMENT_ENDPOINTS)
async def test_achievement_method_http_500_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: AchievementEndpoint
) -> None:
    endpoint.serve(fake_steam, json={"error": "Internal Server Error"}, status=500)

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(steam)

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@achievement_endpoints(ACHIEVEMENT_ENDPOINTS)
async def test_achievement_method_malformed_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: AchievementEndpoint
) -> None:
    endpoint.serve(fake_steam, json=endpoint.malformed)

    with pytest.raises(ResponseParsingError, match=f"Failed to {endpoint.operation}"):
        await endpoint.call(steam)


@achievement_endpoints(ACHIEVEMENT_ENDPOINTS)
async def test_achievement_method_non_json_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: AchievementEndpoint
) -> None:
    endpoint.serve(fake_steam, text="<html>Error</html>", content_type="text/html")

    with pytest.raises(ResponseParsingError, match="Invalid JSON response"):
        await endpoint.call(steam)


@achievement_endpoints(KEY_OR_TOKEN_ENDPOINTS)
async def test_achievement_method_sends_only_the_api_key_when_client_has_both(
    steam: Steam, fake_steam: FakeSteam, endpoint: AchievementEndpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert credential_of(fake_steam.last) == {"key": API_KEY}


@achievement_endpoints(KEY_OR_TOKEN_ENDPOINTS)
async def test_achievement_method_sends_access_token_without_api_key(
    token_only_steam: Steam, fake_steam: FakeSteam, endpoint: AchievementEndpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(token_only_steam)

    assert credential_of(fake_steam.last) == {"access_token": ACCESS_TOKEN}


@achievement_endpoints(KEY_OR_TOKEN_ENDPOINTS)
async def test_achievement_method_without_credential_raises_before_any_request(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: AchievementEndpoint
) -> None:
    endpoint.serve(fake_steam)

    with pytest.raises(AuthenticationError, match="API key or access token"):
        await endpoint.call(anonymous_steam)

    assert fake_steam.requests == []


@pytest.mark.parametrize("bad_id", INVALID_STEAMIDS)
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda steam, steamid: steam.stats.get_achievements_progress(steamid, 440),
            id="get_achievements_progress",
        ),
        pytest.param(
            lambda steam, steamid: steam.stats.get_top_achievements_for_games(
                steamid, 440
            ),
            id="get_top_achievements_for_games",
        ),
    ],
)
async def test_achievement_method_rejects_invalid_steamid_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, Any], Awaitable[object]],
    bad_id: str,
) -> None:
    with pytest.raises(InvalidSteamIDError):
        await call(steam, bad_id)

    assert fake_steam.requests == []


APP_ID_LIST_CALLS = [
    pytest.param(
        lambda steam, appids: steam.stats.get_achievements_progress(STEAMID, appids),
        id="get_achievements_progress",
    ),
    pytest.param(
        lambda steam, appids: steam.stats.get_top_achievements_for_games(
            STEAMID, appids
        ),
        id="get_top_achievements_for_games",
    ),
]


@pytest.mark.parametrize("appids", INVALID_APP_ID_LISTS)
@pytest.mark.parametrize("call", APP_ID_LIST_CALLS)
async def test_achievement_method_rejects_invalid_app_ids_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, Any], Awaitable[object]],
    appids: Any,
) -> None:
    with pytest.raises(InvalidAppIDError):
        await call(steam, appids)

    assert fake_steam.requests == []


@pytest.mark.parametrize("appids", [[], ()], ids=["empty-list", "empty-tuple"])
@pytest.mark.parametrize("call", APP_ID_LIST_CALLS)
async def test_achievement_method_requires_an_app_id(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, Any], Awaitable[object]],
    appids: Any,
) -> None:
    with pytest.raises(ValueError, match="At least one App ID"):
        await call(steam, appids)

    assert fake_steam.requests == []


# -- get_achievements_progress -------------------------------------------------


async def test_get_achievements_progress_posts_inputs_and_key_in_form(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", ACHIEVEMENTS_PROGRESS_PATH, json=ACHIEVEMENTS_PROGRESS)

    await steam.stats.get_achievements_progress(SteamID(STEAMID), [440, 620])

    request = fake_steam.last
    assert sent_pairs(request.form) == {
        "steamid": STEAMID,
        "language": "english",
        "appids[0]": "440",
        "appids[1]": "620",
        "key": API_KEY,
    }
    assert sent_pairs(request.query) == {}


@pytest.mark.parametrize(
    ("appids", "expected"),
    [
        pytest.param(440, {"appids[0]": "440"}, id="one-int"),
        pytest.param((440, 620), {"appids[0]": "440", "appids[1]": "620"}, id="tuple"),
        pytest.param(
            (appid for appid in (620, 440)),
            {"appids[0]": "620", "appids[1]": "440"},
            id="generator",
        ),
    ],
)
async def test_get_achievements_progress_accepts_one_or_several_app_ids(
    steam: Steam, fake_steam: FakeSteam, appids: Any, expected: dict[str, str]
) -> None:
    fake_steam.api("POST", ACHIEVEMENTS_PROGRESS_PATH, json=EMPTY_RESPONSE)

    await steam.stats.get_achievements_progress(int(STEAMID), appids)

    form = sent_pairs(fake_steam.last.form)
    assert {k: v for k, v in form.items() if k.startswith("appids")} == expected
    assert form["steamid"] == STEAMID


@pytest.mark.parametrize(("flag", "sent"), [(True, "1"), (False, "0")])
async def test_get_achievements_progress_sends_language_and_unvetted_flag(
    steam: Steam, fake_steam: FakeSteam, flag: bool, sent: str
) -> None:
    fake_steam.api("POST", ACHIEVEMENTS_PROGRESS_PATH, json=EMPTY_RESPONSE)

    await steam.stats.get_achievements_progress(
        STEAMID, 440, "german", include_unvetted_apps=flag
    )

    form = sent_pairs(fake_steam.last.form)
    assert form["language"] == "german"
    assert form["include_unvetted_apps"] == sent


async def test_get_achievements_progress_parses_every_field(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", ACHIEVEMENTS_PROGRESS_PATH, json=ACHIEVEMENTS_PROGRESS)

    tf2, portal2 = await steam.stats.get_achievements_progress(STEAMID, [440, 620])

    assert isinstance(tf2, AchievementProgress)
    assert tf2.model_dump() == {
        "appid": 440,
        "unlocked": 125,
        "total": 520,
        "percentage": pytest.approx(24.03846),
        "all_unlocked": False,
        "cache_time": 1759489200,
        "vetted": True,
    }
    assert (portal2.appid, portal2.unlocked, portal2.total) == (620, 51, 51)
    assert portal2.percentage == 100.0
    assert portal2.all_unlocked is True


async def test_get_achievements_progress_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", ACHIEVEMENTS_PROGRESS_PATH, json=EMPTY_RESPONSE)

    assert await steam.stats.get_achievements_progress(STEAMID, 440) == []


async def test_achievement_progress_defaults_every_field() -> None:
    assert AchievementProgress.model_validate({"appid": 4000}).model_dump() == {
        "appid": 4000,
        "unlocked": 0,
        "total": 0,
        "percentage": 0.0,
        "all_unlocked": False,
        "cache_time": 0,
        "vetted": False,
    }


# -- get_game_achievements -----------------------------------------------------


async def test_get_game_achievements_sends_appid_and_language_without_credential(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GAME_ACHIEVEMENTS_PATH, json=GAME_ACHIEVEMENTS)

    await steam.stats.get_game_achievements(440, language="german")

    request = fake_steam.last
    assert sent_pairs(request.query) == {"appid": "440", "language": "german"}
    assert credential_of(request) == {}
    assert "Cookie" not in request.headers


async def test_get_game_achievements_works_without_any_credential(
    anonymous_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GAME_ACHIEVEMENTS_PATH, json=GAME_ACHIEVEMENTS)

    result = await anonymous_steam.stats.get_game_achievements(440)

    assert len(result.achievements) == 2
    assert sent_pairs(fake_steam.last.query) == {
        "appid": "440",
        "language": "english",
    }


async def test_get_game_achievements_parses_achievements(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GAME_ACHIEVEMENTS_PATH, json=GAME_ACHIEVEMENTS)

    result = await steam.stats.get_game_achievements(440)

    assert isinstance(result, GameAchievements)
    every_class, team_doctor = result.achievements
    assert isinstance(every_class, GameAchievement)
    assert every_class.internal_name == "TF_PLAY_GAME_EVERYCLASS"
    assert every_class.localized_name == "Head of the Class"
    assert every_class.localized_desc == "Play a complete round with every class."
    assert every_class.icon == "tf_play_game_everyclass.jpg"
    assert every_class.icon_gray == "tf_play_game_everyclass_bw.jpg"
    assert every_class.hidden is False
    assert every_class.player_percent_unlocked == "71.9"
    assert every_class.percent_unlocked == pytest.approx(71.9)
    assert team_doctor.percent_unlocked == pytest.approx(23.4)
    assert every_class.progress_type == EAchievementProgressType.INVALID
    assert (result.schema_version, result.schema_hash, result.groups) == (0, 0, [])


async def test_get_game_achievements_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GAME_ACHIEVEMENTS_PATH, json=EMPTY_RESPONSE)

    result = await steam.stats.get_game_achievements(440)

    assert result == GameAchievements()
    assert result.achievements == result.groups == []


async def test_game_achievements_parse_progress_and_groups() -> None:
    # Parts the fixture does not show, shaped as
    # CPlayer_GetGameAchievements_Response in SteamDatabase/Protobufs.
    result = GameAchievements.model_validate(
        {
            "achievements": [
                {
                    "internal_name": "ACH_COLLECT_100",
                    "hidden": True,
                    "internal_key": 12,
                    "min_progress_int": 0,
                    "max_progress_int": 100,
                    "groupid": 2,
                    "archived": True,
                    "progress_type": 1,
                    "min_progress_float": 0.5,
                    "max_progress_float": 99.5,
                }
            ],
            "schema_version": 7,
            "groups": [
                {
                    "groupid": 2,
                    "localized_name": "DLC",
                    "dlcappid": 1234560,
                    "archived": False,
                    "developeronly": False,
                    "order": 1,
                    "ispublic": True,
                    "total_achievements": 10,
                    "completion_achievements": 8,
                }
            ],
            "schema_hash": 3735928559,
        }
    )

    (achievement,) = result.achievements
    assert achievement.hidden is True
    assert (achievement.internal_key, achievement.groupid) == (12, 2)
    assert (achievement.min_progress_int, achievement.max_progress_int) == (0, 100)
    assert achievement.progress_type == EAchievementProgressType.INT
    assert (achievement.min_progress_float, achievement.max_progress_float) == (
        0.5,
        99.5,
    )
    assert achievement.archived is True
    assert achievement.percent_unlocked is None
    (group,) = result.groups
    assert (group.groupid, group.localized_name, group.dlcappid) == (2, "DLC", 1234560)
    assert (group.total_achievements, group.completion_achievements) == (10, 8)
    assert group.ispublic is True
    assert (result.schema_version, result.schema_hash) == (7, 3735928559)


@pytest.mark.parametrize(
    ("text", "expected"),
    [("26.8", 26.8), ("0.1", 0.1), ("100", 100.0), ("", None), ("n/a", None)],
)
def test_percent_unlocked_reads_steams_string(
    text: str, expected: float | None
) -> None:
    assert GameAchievement(player_percent_unlocked=text).percent_unlocked == expected
    assert TopAchievement(player_percent_unlocked=text).percent_unlocked == expected


@pytest.mark.parametrize("bad_id", INVALID_APP_IDS)
async def test_get_game_achievements_rejects_invalid_app_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, bad_id: Any
) -> None:
    with pytest.raises(InvalidAppIDError):
        await steam.stats.get_game_achievements(bad_id)

    assert fake_steam.requests == []


# -- get_top_achievements_for_games --------------------------------------------


async def test_get_top_achievements_for_games_sends_inputs_in_query(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TOP_ACHIEVEMENTS_PATH, json=TOP_ACHIEVEMENTS)

    await steam.stats.get_top_achievements_for_games(
        STEAMID, [1342330, 440], "schinese", max_achievements=8
    )

    request = fake_steam.last
    assert sent_pairs(request.query) == {
        "steamid": STEAMID,
        "language": "schinese",
        "max_achievements": "8",
        "appids[0]": "1342330",
        "appids[1]": "440",
        "key": API_KEY,
    }
    assert request.form == {}


async def test_get_top_achievements_for_games_leaves_out_max_achievements(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TOP_ACHIEVEMENTS_PATH, json=TOP_ACHIEVEMENTS)

    await steam.stats.get_top_achievements_for_games(STEAMID, 1342330)

    assert sent_pairs(fake_steam.last.query) == {
        "steamid": STEAMID,
        "language": "english",
        "appids[0]": "1342330",
        "key": API_KEY,
    }


@pytest.mark.parametrize("bad", [0, -1, True, 1.5, "8"])
async def test_get_top_achievements_for_games_rejects_bad_max_before_any_request(
    steam: Steam, fake_steam: FakeSteam, bad: Any
) -> None:
    with pytest.raises(ValueError, match="max_achievements"):
        await steam.stats.get_top_achievements_for_games(
            STEAMID, 440, max_achievements=bad
        )

    assert fake_steam.requests == []


async def test_get_top_achievements_for_games_parses_real_reply(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TOP_ACHIEVEMENTS_PATH, json=TOP_ACHIEVEMENTS)

    (game,) = await steam.stats.get_top_achievements_for_games(STEAMID, 1342330)

    assert isinstance(game, TopAchievementsGame)
    assert (game.appid, game.total_achievements) == (1342330, 73)
    first, second = game.achievements
    assert isinstance(first, TopAchievement)
    assert first.model_dump() == {
        "statid": 1,
        "bit": 6,
        "name": "Super Lario World",
        "desc": "Create an platformer with a rating of at least 70%.",
        "icon": "27b8689b12105d9fafbee6c14067ab33f7fa51f6.jpg",
        "icon_gray": "0172bba081531c548774003d1efca16d312b991c.jpg",
        "hidden": False,
        "player_percent_unlocked": "26.8",
    }
    assert (second.statid, second.bit, second.name) == (3, 7, "Shopping Tour II")
    assert second.percent_unlocked == pytest.approx(15.1)


async def test_get_top_achievements_for_games_parses_empty_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", TOP_ACHIEVEMENTS_PATH, json=EMPTY_RESPONSE)

    assert await steam.stats.get_top_achievements_for_games(STEAMID, 440) == []


async def test_top_achievements_game_defaults_every_field() -> None:
    game = TopAchievementsGame.model_validate({"appid": 440})

    assert (game.total_achievements, game.achievements) == (0, [])
    assert TopAchievement().model_dump() == {
        "statid": 0,
        "bit": 0,
        "name": "",
        "desc": "",
        "icon": "",
        "icon_gray": "",
        "hidden": False,
        "player_percent_unlocked": "",
    }


@pytest.mark.parametrize(
    "bad_id",
    [
        pytest.param(True, id="bool"),
        pytest.param(STEAMID.encode(), id="bytes"),
        pytest.param(float(STEAMID), id="float"),
        pytest.param(None, id="none"),
    ],
)
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(
            lambda steam, steamid: steam.stats.get_achievements_progress(steamid, 440),
            id="get_achievements_progress",
        ),
        pytest.param(
            lambda steam, steamid: steam.stats.get_top_achievements_for_games(
                steamid, 440
            ),
            id="get_top_achievements_for_games",
        ),
    ],
)
async def test_achievement_method_rejects_non_id_types_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, Any], Awaitable[object]],
    bad_id: Any,
) -> None:
    with pytest.raises(InvalidSteamIDError):
        await call(steam, bad_id)

    assert fake_steam.requests == []
