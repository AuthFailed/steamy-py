"""Tests for ``StatsAPI``: player counts, news, user and global statistics."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

import pytest

from steamy_py import (
    GameNotFoundError,
    InvalidAppIDError,
    InvalidSteamIDError,
    NewsItem,
    PlayerCount,
    PrivateProfileError,
    Settings,
    Steam,
    SteamAPIError,
    UserStat,
)
from steamy_py.models.stats import GlobalAchievementStat, GlobalStat, UserAchievement
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
