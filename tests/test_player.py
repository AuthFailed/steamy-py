"""Tests for ``PlayerAPI``: ISteamUser summaries, friends, bans and vanity URLs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from steamy_py import (
    Friend,
    InvalidSteamIDError,
    PlayerBan,
    PlayerSummary,
    PrivateProfileError,
    Settings,
    Steam,
    SteamAPIError,
)
from steamy_py.models.player import CommunityVisibilityState, PersonaState
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

SUMMARIES_PATH = "/ISteamUser/GetPlayerSummaries/v2/"
FRIENDS_PATH = "/ISteamUser/GetFriendList/v1/"
BANS_PATH = "/ISteamUser/GetPlayerBans/v1/"
VANITY_PATH = "/ISteamUser/ResolveVanityURL/v1/"

# SteamID64 of an individual account = this base + the 32-bit account id.
INDIVIDUAL_BASE = 76561197960265728
FRAG_MASTER = "76561198012345678"
QUIET_ONE = "76561198087654321"
VALVE_GROUP = "103582791429521412"

NO_PLAYERS: dict[str, Any] = {"response": {"players": []}}
NO_FRIENDS: dict[str, Any] = {"friendslist": {"friends": []}}
NO_BANS: dict[str, Any] = {"players": []}
NO_MATCH: dict[str, Any] = {"response": {"success": 42, "message": "No match"}}
ROBIN_RESOLVED: dict[str, Any] = {"response": {"steamid": STEAMID, "success": 1}}

# What GetFriendList answers for a user whose friends list is not public.
UNAUTHORIZED_HTML = (
    "<html><head><title>Unauthorized</title></head>"
    "<body><h1>Unauthorized</h1></body></html>"
)

DEFAULT_AVATAR = (
    "https://avatars.steamstatic.com/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"
)

XFAIL_HIGH_ACCOUNT_IDS = pytest.mark.xfail(
    raises=InvalidSteamIDError,
    reason="#23: ids above 76561199999999999 fail the '7656119' prefix check",
)

Call = Callable[[Steam], Awaitable[object]]
SteamIDCall = Callable[[Steam, str], Awaitable[object]]


def player(steamid: str = STEAMID, **fields: Any) -> dict[str, Any]:
    """A GetPlayerSummaries entry with only the fields every profile has."""
    return {
        "steamid": steamid,
        "communityvisibilitystate": 3,
        "profilestate": 1,
        "personaname": "player",
        "profileurl": f"https://steamcommunity.com/profiles/{steamid}/",
        "avatar": f"{DEFAULT_AVATAR}.jpg",
        "avatarmedium": f"{DEFAULT_AVATAR}_medium.jpg",
        "avatarfull": f"{DEFAULT_AVATAR}_full.jpg",
        "avatarhash": "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb",
        "personastate": 0,
        **fields,
    }


def account(account_id: int) -> str:
    """SteamID64 of the individual account with ``account_id``."""
    return str(INDIVIDUAL_BASE + account_id)


def assert_sent_with_api_key(request: RecordedRequest, path: str) -> None:
    """``request`` is a GET to ``path`` carrying the API key and nothing else."""
    assert request.method == "GET"
    assert request.path == path
    assert request.query.getall("key") == [API_KEY]
    assert "access_token" not in request.query
    assert "Authorization" not in request.headers


# Every public method with a reply that parses, for the cross-cutting checks.
ENDPOINTS = [
    pytest.param(
        lambda steam: steam.player.get_player_summaries([STEAMID]),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summaries",
    ),
    pytest.param(
        lambda steam: steam.player.get_player_summary(STEAMID),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summary",
    ),
    pytest.param(
        lambda steam: steam.player.get_friends_list(STEAMID),
        FRIENDS_PATH,
        NO_FRIENDS,
        id="get_friends_list",
    ),
    pytest.param(
        lambda steam: steam.player.get_player_bans(STEAMID),
        BANS_PATH,
        NO_BANS,
        id="get_player_bans",
    ),
    pytest.param(
        lambda steam: steam.player.resolve_vanity_url("robinwalker"),
        VANITY_PATH,
        NO_MATCH,
        id="resolve_vanity_url",
    ),
]

# Every method that takes Steam IDs, called with ``steamid`` in the batch.
STEAMID_CALLS = [
    pytest.param(
        lambda steam, steamid: steam.player.get_player_summaries(steamid),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summaries",
    ),
    pytest.param(
        lambda steam, steamid: steam.player.get_player_summaries([STEAMID, steamid]),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summaries-list",
    ),
    pytest.param(
        lambda steam, steamid: steam.player.get_player_summary(steamid),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summary",
    ),
    pytest.param(
        lambda steam, steamid: steam.player.get_friends_list(steamid),
        FRIENDS_PATH,
        NO_FRIENDS,
        id="get_friends_list",
    ),
    pytest.param(
        lambda steam, steamid: steam.player.get_player_bans(steamid),
        BANS_PATH,
        NO_BANS,
        id="get_player_bans",
    ),
    pytest.param(
        lambda steam, steamid: steam.player.get_player_bans([steamid, STEAMID]),
        BANS_PATH,
        NO_BANS,
        id="get_player_bans-list",
    ),
]

INVALID_STEAMIDS = [
    pytest.param("", id="empty"),
    pytest.param("robinwalker", id="vanity-name"),
    pytest.param("STEAM_0:0:84901", id="steam2-format"),
    pytest.param("[U:1:169802]", id="steam3-format"),
    pytest.param(STEAMID[:-1], id="16-digits"),
    pytest.param(STEAMID + "0", id="18-digits"),
    pytest.param(VALVE_GROUP, id="group-steamid"),
    pytest.param("12345678901234567", id="17-digits-not-a-steamid"),
    pytest.param(f" {STEAMID}", id="leading-space"),
    pytest.param(f"{STEAMID}\n", id="trailing-newline"),
    pytest.param("-" + STEAMID[1:], id="negative"),
]


# -- credentials and errors shared by every endpoint ---------------------------


@pytest.mark.parametrize(("call", "path", "reply"), ENDPOINTS)
async def test_endpoint_sends_api_key_not_access_token(
    steam: Steam, fake_steam: FakeSteam, call: Call, path: str, reply: dict[str, Any]
) -> None:
    fake_steam.api("GET", path, json=reply)

    await call(steam)

    assert len(fake_steam.requests) == 1
    assert_sent_with_api_key(fake_steam.last, path)


@pytest.mark.parametrize(("call", "path", "reply"), ENDPOINTS)
async def test_http_error_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, call: Call, path: str, reply: dict[str, Any]
) -> None:
    fake_steam.api("GET", path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await call(steam)

    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)


INVALID_STRUCTURE = "Invalid response structure from Steam API"


@pytest.mark.parametrize(
    ("call", "path", "body", "message"),
    [
        pytest.param(
            lambda steam: steam.player.get_player_summaries(STEAMID),
            SUMMARIES_PATH,
            {},
            INVALID_STRUCTURE,
            id="summaries-no-response",
        ),
        pytest.param(
            lambda steam: steam.player.get_player_summaries(STEAMID),
            SUMMARIES_PATH,
            {"response": {}},
            "Failed to get player summaries",
            id="summaries-no-players",
        ),
        pytest.param(
            lambda steam: steam.player.get_player_summaries(STEAMID),
            SUMMARIES_PATH,
            {"response": {"players": [{"steamid": STEAMID}]}},
            "Failed to get player summaries",
            id="summaries-truncated-player",
        ),
        pytest.param(
            lambda steam: steam.player.get_friends_list(STEAMID),
            FRIENDS_PATH,
            {"friendslist": {"friends": [{"relationship": "friend"}]}},
            "Failed to get friends list",
            id="friends-entry-without-steamid",
        ),
        pytest.param(
            lambda steam: steam.player.get_player_bans(STEAMID),
            BANS_PATH,
            {},
            INVALID_STRUCTURE,
            id="bans-no-players",
        ),
        pytest.param(
            lambda steam: steam.player.resolve_vanity_url("robinwalker"),
            VANITY_PATH,
            {},
            INVALID_STRUCTURE,
            id="vanity-no-response",
        ),
        pytest.param(
            lambda steam: steam.player.resolve_vanity_url("robinwalker"),
            VANITY_PATH,
            {"response": {"steamid": STEAMID}},
            "Failed to resolve vanity URL",
            id="vanity-no-success",
        ),
    ],
)
async def test_unexpected_body_is_raised_as_steam_api_error(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    body: dict[str, Any],
    message: str,
) -> None:
    fake_steam.api("GET", path, json=body)

    with pytest.raises(SteamAPIError, match=message) as excinfo:
        await call(steam)

    # The plain wrapper, not a more specific subclass such as PrivateProfileError.
    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code is None
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(("call", "path", "reply"), ENDPOINTS)
async def test_endpoint_works_with_api_key_only(
    settings: Settings,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
) -> None:
    fake_steam.api("GET", path, json=reply)

    async with Steam(api_key=API_KEY, settings=settings) as steam:
        await call(steam)

    assert_sent_with_api_key(fake_steam.last, path)


@pytest.mark.parametrize(("call", "path", "reply"), ENDPOINTS)
async def test_endpoint_without_api_key_never_sends_access_token(
    settings: Settings,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
) -> None:
    """The access token must not be used as a fallback for key-only endpoints."""
    fake_steam.api("GET", path, json=reply)

    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as steam:
        with pytest.raises((ValueError, SteamAPIError), match="API key is required"):
            await call(steam)

    assert fake_steam.requests == []


# -- Steam ID validation -------------------------------------------------------


@pytest.mark.parametrize("bad_id", INVALID_STEAMIDS)
@pytest.mark.parametrize(("call", "path", "reply"), STEAMID_CALLS)
async def test_invalid_steamid_is_rejected_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: SteamIDCall,
    path: str,
    reply: dict[str, Any],
    bad_id: str,
) -> None:
    fake_steam.api("GET", path, json=reply)

    with pytest.raises(InvalidSteamIDError) as excinfo:
        await call(steam, bad_id)

    assert excinfo.value.steamid == bad_id
    assert fake_steam.requests == []


@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param(STEAMID, id="robin"),
        pytest.param(account(1), id="lowest-account-id"),
        pytest.param("76561199999999999", id="76561199999999999"),
        pytest.param(
            "76561200000000000", id="76561200000000000", marks=XFAIL_HIGH_ACCOUNT_IDS
        ),
        pytest.param(
            account(2**32 - 1), id="highest-account-id", marks=XFAIL_HIGH_ACCOUNT_IDS
        ),
    ],
)
async def test_valid_individual_steamid_is_sent(
    steam: Steam, fake_steam: FakeSteam, steamid: str
) -> None:
    fake_steam.api(
        "GET", SUMMARIES_PATH, json={"response": {"players": [player(steamid)]}}
    )

    summary = await steam.player.get_player_summary(steamid)

    assert summary is not None
    assert summary.steamid == steamid
    assert fake_steam.last.params["steamids"] == steamid


@pytest.mark.xfail(
    raises=pytest.fail.Exception,
    reason="#23: str.isdigit() accepts non-ASCII digits",
)
async def test_steamid_with_non_ascii_digit_is_rejected(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fullwidth_zero = "\N{FULLWIDTH DIGIT ZERO}"
    fake_steam.api("GET", SUMMARIES_PATH, json=NO_PLAYERS)

    with pytest.raises(InvalidSteamIDError):
        await steam.player.get_player_summary(STEAMID[:-1] + fullwidth_zero)

    assert fake_steam.requests == []


# -- batch size limit ----------------------------------------------------------


BATCH_CALLS = [
    pytest.param(
        lambda steam, ids: steam.player.get_player_summaries(ids),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summaries",
    ),
    pytest.param(
        lambda steam, ids: steam.player.get_player_bans(ids),
        BANS_PATH,
        NO_BANS,
        id="get_player_bans",
    ),
]


@pytest.mark.parametrize(("call", "path", "reply"), BATCH_CALLS)
async def test_batch_of_100_ids_is_sent_in_one_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, list[str]], Awaitable[object]],
    path: str,
    reply: dict[str, Any],
) -> None:
    ids = [account(n) for n in range(1, 101)]
    fake_steam.api("GET", path, json=reply)

    await call(steam, ids)

    assert len(fake_steam.requests) == 1
    assert fake_steam.last.query.getall("steamids") == [",".join(ids)]


@pytest.mark.parametrize(("call", "path", "reply"), BATCH_CALLS)
async def test_batch_of_101_ids_is_rejected_before_any_request(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, list[str]], Awaitable[object]],
    path: str,
    reply: dict[str, Any],
) -> None:
    fake_steam.api("GET", path, json=reply)

    with pytest.raises(ValueError, match="Maximum 100"):
        await call(steam, [account(n) for n in range(1, 102)])

    assert fake_steam.requests == []


# -- GetPlayerSummaries --------------------------------------------------------


async def test_get_player_summaries_sends_single_id(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=NO_PLAYERS)

    await steam.player.get_player_summaries(STEAMID)

    assert_sent_with_api_key(fake_steam.last, SUMMARIES_PATH)
    assert fake_steam.last.params == {"steamids": STEAMID, "key": API_KEY}


async def test_get_player_summaries_comma_joins_ids_in_order(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=load_fixture("player_summaries.json"))

    summaries = await steam.player.get_player_summaries(
        [STEAMID, FRAG_MASTER, QUIET_ONE]
    )

    assert fake_steam.last.query.getall("steamids") == [
        f"{STEAMID},{FRAG_MASTER},{QUIET_ONE}"
    ]
    assert [s.steamid for s in summaries] == [STEAMID, FRAG_MASTER, QUIET_ONE]
    assert all(isinstance(s, PlayerSummary) for s in summaries)


async def test_get_player_summaries_parses_public_profile(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=load_fixture("player_summaries.json"))

    robin = (
        await steam.player.get_player_summaries([STEAMID, FRAG_MASTER, QUIET_ONE])
    )[0]

    assert robin.steamid == STEAMID
    assert robin.personaname == "Robin"
    assert robin.realname == "Robin Walker"
    assert robin.profileurl == "https://steamcommunity.com/id/robinwalker/"
    avatar = "https://avatars.steamstatic.com/81b5478529dce13bf24b55ac42c1af7058aaf7a9"
    assert robin.avatar == f"{avatar}.jpg"
    assert robin.avatarmedium == f"{avatar}_medium.jpg"
    assert robin.avatarfull == f"{avatar}_full.jpg"
    assert robin.communityvisibilitystate == CommunityVisibilityState.PUBLIC
    assert robin.personastate == PersonaState.OFFLINE
    assert robin.profilestate == 1
    assert robin.commentpermission == 1
    assert robin.lastlogoff == 1790903215
    assert robin.primaryclanid == "103582791429521412"
    assert robin.timecreated == 1063407589
    assert (robin.loccountrycode, robin.locstatecode, robin.loccityid) == (
        "US",
        "WA",
        3961,
    )
    assert robin.is_public
    assert not robin.is_online
    assert not robin.is_in_game


async def test_get_player_summaries_parses_player_in_game(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=load_fixture("player_summaries.json"))

    in_game = (
        await steam.player.get_player_summaries([STEAMID, FRAG_MASTER, QUIET_ONE])
    )[1]

    assert in_game.steamid == FRAG_MASTER
    assert in_game.personastate == PersonaState.ONLINE
    assert in_game.gameid == "730"
    assert in_game.gameextrainfo == "Counter-Strike 2"
    assert in_game.gameserverip == "162.254.197.36:27015"
    assert in_game.realname is None
    assert in_game.is_online
    assert in_game.is_in_game


async def test_get_player_summaries_private_profile_leaves_optional_fields_none(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=load_fixture("player_summaries.json"))

    private = (
        await steam.player.get_player_summaries([STEAMID, FRAG_MASTER, QUIET_ONE])
    )[2]

    assert private.steamid == QUIET_ONE
    assert private.personaname == "quiet_one"
    assert private.communityvisibilitystate == CommunityVisibilityState.PRIVATE
    assert not private.is_public
    for name in (
        "realname",
        "primaryclanid",
        "timecreated",
        "lastlogoff",
        "commentpermission",
        "gameid",
        "gameextrainfo",
        "gameserverip",
        "loccountrycode",
        "locstatecode",
        "loccityid",
    ):
        assert getattr(private, name) is None, name


async def test_get_player_summaries_without_profilestate(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    """A profile that was never set up has no ``profilestate``."""
    entry = player()
    del entry["profilestate"]
    fake_steam.api("GET", SUMMARIES_PATH, json={"response": {"players": [entry]}})

    [summary] = await steam.player.get_player_summaries(STEAMID)

    assert summary.profilestate is None


@pytest.mark.parametrize(
    ("value", "state", "online"),
    [
        (0, PersonaState.OFFLINE, False),
        (1, PersonaState.ONLINE, True),
        (2, PersonaState.BUSY, True),
        (3, PersonaState.AWAY, True),
        (4, PersonaState.SNOOZE, True),
        (5, PersonaState.LOOKING_TO_TRADE, True),
        (6, PersonaState.LOOKING_TO_PLAY, True),
    ],
)
async def test_get_player_summaries_parses_persona_state(
    steam: Steam, fake_steam: FakeSteam, value: int, state: PersonaState, online: bool
) -> None:
    fake_steam.api(
        "GET",
        SUMMARIES_PATH,
        json={"response": {"players": [player(personastate=value)]}},
    )

    [summary] = await steam.player.get_player_summaries(STEAMID)

    assert summary.personastate == state
    assert summary.is_online is online


@pytest.mark.parametrize(
    ("value", "visibility", "public"),
    [
        (1, CommunityVisibilityState.PRIVATE, False),
        (2, CommunityVisibilityState.FRIENDS_ONLY, False),
        (3, CommunityVisibilityState.PUBLIC, True),
    ],
)
async def test_get_player_summaries_parses_visibility(
    steam: Steam,
    fake_steam: FakeSteam,
    value: int,
    visibility: CommunityVisibilityState,
    public: bool,
) -> None:
    fake_steam.api(
        "GET",
        SUMMARIES_PATH,
        json={"response": {"players": [player(communityvisibilitystate=value)]}},
    )

    [summary] = await steam.player.get_player_summaries(STEAMID)

    assert summary.communityvisibilitystate == visibility
    assert summary.is_public is public


async def test_get_player_summary_returns_the_player(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        SUMMARIES_PATH,
        json={"response": {"players": [player(personaname="Robin")]}},
    )

    summary = await steam.player.get_player_summary(STEAMID)

    assert isinstance(summary, PlayerSummary)
    assert summary.steamid == STEAMID
    assert summary.personaname == "Robin"
    assert_sent_with_api_key(fake_steam.last, SUMMARIES_PATH)
    assert fake_steam.last.params == {"steamids": STEAMID, "key": API_KEY}


async def test_get_player_summary_returns_none_for_unknown_account(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=NO_PLAYERS)

    assert await steam.player.get_player_summary(account(1_999_999_999)) is None


# -- GetFriendList -------------------------------------------------------------


async def test_get_friends_list_requests_friend_relationship_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json=NO_FRIENDS)

    await steam.player.get_friends_list(STEAMID)

    assert_sent_with_api_key(fake_steam.last, FRIENDS_PATH)
    assert fake_steam.last.params == {
        "steamid": STEAMID,
        "relationship": "friend",
        "key": API_KEY,
    }


async def test_get_friends_list_passes_relationship(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json=NO_FRIENDS)

    await steam.player.get_friends_list(STEAMID, relationship="all")

    assert fake_steam.last.params["relationship"] == "all"


async def test_get_friends_list_parses_friends(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json=load_fixture("player_friends.json"))

    friends = await steam.player.get_friends_list(STEAMID)

    assert all(isinstance(f, Friend) for f in friends)
    assert [(f.steamid, f.relationship, f.friend_since) for f in friends] == [
        ("76561197960265731", "friend", 0),
        ("76561197960265738", "friend", 0),
        ("76561197960265740", "friend", 1258849452),
        (FRAG_MASTER, "friend", 1612137600),
    ]


async def test_friend_since_datetime(steam: Steam, fake_steam: FakeSteam) -> None:
    """Steam reports 0 for friendships older than the field (pre-2009)."""
    fake_steam.api("GET", FRIENDS_PATH, json=load_fixture("player_friends.json"))

    friends = await steam.player.get_friends_list(STEAMID)

    assert friends[0].friend_since_datetime is None
    since = friends[2].friend_since_datetime
    assert since is not None
    assert since.timestamp() == 1258849452


async def test_get_friends_list_with_no_friends(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json=NO_FRIENDS)

    assert await steam.player.get_friends_list(STEAMID) == []


async def test_get_friends_list_without_friendslist_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json={})

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.player.get_friends_list(STEAMID)

    assert excinfo.value.steamid == STEAMID
    assert_sent_with_api_key(fake_steam.last, FRIENDS_PATH)


@pytest.mark.xfail(
    raises=SteamAPIError,
    reason="#20: HTTP 401 for a private friends list surfaces as plain SteamAPIError",
)
async def test_get_friends_list_private_profile_401_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        FRIENDS_PATH,
        status=401,
        text=UNAUTHORIZED_HTML,
        content_type="text/html",
    )

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.player.get_friends_list(STEAMID)

    assert excinfo.value.steamid == STEAMID


# -- GetPlayerBans -------------------------------------------------------------


async def test_get_player_bans_sends_comma_joined_ids(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BANS_PATH, json=NO_BANS)

    assert await steam.player.get_player_bans([STEAMID, FRAG_MASTER]) == []

    assert_sent_with_api_key(fake_steam.last, BANS_PATH)
    assert fake_steam.last.params == {
        "steamids": f"{STEAMID},{FRAG_MASTER}",
        "key": API_KEY,
    }


@pytest.mark.xfail(
    raises=SteamAPIError,
    reason="#20: PlayerBan expects snake_case keys; Steam sends PascalCase",
)
async def test_get_player_bans_parses_real_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BANS_PATH, json=load_fixture("player_bans.json"))

    clean, banned = await steam.player.get_player_bans([STEAMID, FRAG_MASTER])

    assert isinstance(clean, PlayerBan)
    assert clean.steamid == STEAMID
    assert not clean.community_banned
    assert not clean.vac_banned
    assert clean.economy_ban == "none"
    assert not clean.is_banned
    assert not clean.has_economy_ban

    assert banned.steamid == FRAG_MASTER
    assert banned.vac_banned
    assert banned.number_of_vac_bans == 1
    assert banned.days_since_last_ban == 412
    assert banned.number_of_game_bans == 2
    assert banned.economy_ban == "probation"
    assert banned.is_banned
    assert banned.has_economy_ban


# -- ResolveVanityURL ----------------------------------------------------------


async def test_resolve_vanity_url_returns_steamid(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", VANITY_PATH, json=ROBIN_RESOLVED)

    assert await steam.player.resolve_vanity_url("robinwalker") == STEAMID

    assert_sent_with_api_key(fake_steam.last, VANITY_PATH)
    assert fake_steam.last.params == {
        "vanityurl": "robinwalker",
        "url_type": "1",
        "key": API_KEY,
    }


async def test_resolve_vanity_url_returns_none_when_no_match(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", VANITY_PATH, json=NO_MATCH)

    assert await steam.player.resolve_vanity_url("no-such-profile-here") is None


async def test_resolve_vanity_url_passes_url_type(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", VANITY_PATH, json={"response": {"steamid": VALVE_GROUP, "success": 1}}
    )

    assert await steam.player.resolve_vanity_url("valve", url_type=2) == VALVE_GROUP

    assert fake_steam.last.params["url_type"] == "2"


@pytest.mark.parametrize(
    "url",
    [
        "https://steamcommunity.com/id/robinwalker",
        "http://steamcommunity.com/id/robinwalker",
        "steamcommunity.com/id/robinwalker",
        pytest.param(
            "https://steamcommunity.com/id/robinwalker/",
            marks=pytest.mark.xfail(
                raises=AssertionError,
                reason="#20: trailing slash leaves an empty vanityurl",
            ),
        ),
    ],
)
async def test_resolve_vanity_url_accepts_profile_url(
    steam: Steam, fake_steam: FakeSteam, url: str
) -> None:
    fake_steam.api("GET", VANITY_PATH, json=ROBIN_RESOLVED)

    steamid = await steam.player.resolve_vanity_url(url)

    assert fake_steam.last.params["vanityurl"] == "robinwalker"
    assert steamid == STEAMID
