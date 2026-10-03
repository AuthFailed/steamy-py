"""Tests for ``steam.users``: ISteamUser summaries, friends, bans, vanity URLs and
groups, and the IPlayerService profile methods (badges, levels, badge progress,
link details, equipped profile items).

Fixtures: users_steam_level_distribution.json is a value Steam returned for
level 10 (recorded in woctezuma/steam-player-level-percentiles), and
users_user_group_list.json real group ids (from almic/steam-js-api's docs) in
the reply shape published clients parse. users_community_badge_progress.json,
users_player_link_details.json and users_profile_items_equipped.json are built
from Steam's protobufs and the replies other clients publish; no recorded
replies for them were found.
"""

from __future__ import annotations

import base64
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    Friend,
    InvalidSteamIDError,
    PlayerBan,
    PlayerSummary,
    PrivateProfileError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
    SteamID,
)
from steamy_py.models.player import (
    CommunityBadgeQuest,
    CommunityVisibilityState,
    PersonaState,
    PlayerLinkDetails,
    ProfileItem,
    ProfileItemColor,
    ProfileItemsEquipped,
)
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
GROUP_LIST_PATH = "/ISteamUser/GetUserGroupList/v1/"

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
GROUP_LIST: dict[str, Any] = load_fixture("users_user_group_list.json")

# What GetFriendList answers for a user whose friends list is not public.
UNAUTHORIZED_HTML = (
    "<html><head><title>Unauthorized</title></head>"
    "<body><h1>Unauthorized</h1></body></html>"
)

DEFAULT_AVATAR = (
    "https://avatars.steamstatic.com/fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb"
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
        lambda steam: steam.users.get_player_summaries([STEAMID]),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summaries",
    ),
    pytest.param(
        lambda steam: steam.users.get_player_summary(STEAMID),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summary",
    ),
    pytest.param(
        lambda steam: steam.users.get_friends_list(STEAMID),
        FRIENDS_PATH,
        NO_FRIENDS,
        id="get_friends_list",
    ),
    pytest.param(
        lambda steam: steam.users.get_player_bans(STEAMID),
        BANS_PATH,
        NO_BANS,
        id="get_player_bans",
    ),
    pytest.param(
        lambda steam: steam.users.resolve_vanity_url("robinwalker"),
        VANITY_PATH,
        NO_MATCH,
        id="resolve_vanity_url",
    ),
    pytest.param(
        lambda steam: steam.users.get_user_group_list(STEAMID),
        GROUP_LIST_PATH,
        GROUP_LIST,
        id="get_user_group_list",
    ),
]

# Every method that takes Steam IDs, called with ``steamid`` in the batch.
STEAMID_CALLS = [
    pytest.param(
        lambda steam, steamid: steam.users.get_player_summaries(steamid),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summaries",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_player_summaries([STEAMID, steamid]),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summaries-list",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_player_summary(steamid),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summary",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_friends_list(steamid),
        FRIENDS_PATH,
        NO_FRIENDS,
        id="get_friends_list",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_player_bans(steamid),
        BANS_PATH,
        NO_BANS,
        id="get_player_bans",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_player_bans([steamid, STEAMID]),
        BANS_PATH,
        NO_BANS,
        id="get_player_bans-list",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_user_group_list(steamid),
        GROUP_LIST_PATH,
        GROUP_LIST,
        id="get_user_group_list",
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
    pytest.param(str(INDIVIDUAL_BASE), id="account-id-0"),
    pytest.param("76561190000000000", id="7656119-prefix-below-base"),
    pytest.param(str(INDIVIDUAL_BASE + 2**32), id="account-id-overflow"),
    pytest.param(str(INDIVIDUAL_BASE - 2**32 + 169802), id="instance-0"),
    pytest.param(str(INDIVIDUAL_BASE + (1 << 56) + 169802), id="universe-2"),
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
            lambda steam: steam.users.get_player_summaries(STEAMID),
            SUMMARIES_PATH,
            {},
            INVALID_STRUCTURE,
            id="summaries-no-response",
        ),
        pytest.param(
            lambda steam: steam.users.get_player_summaries(STEAMID),
            SUMMARIES_PATH,
            {"response": {}},
            "Failed to get player summaries",
            id="summaries-no-players",
        ),
        pytest.param(
            lambda steam: steam.users.get_player_summaries(STEAMID),
            SUMMARIES_PATH,
            {"response": {"players": [{"steamid": STEAMID}]}},
            "Failed to get player summaries",
            id="summaries-truncated-player",
        ),
        pytest.param(
            lambda steam: steam.users.get_friends_list(STEAMID),
            FRIENDS_PATH,
            {"friendslist": {"friends": [{"relationship": "friend"}]}},
            "Failed to get friends list",
            id="friends-entry-without-steamid",
        ),
        pytest.param(
            lambda steam: steam.users.get_player_bans(STEAMID),
            BANS_PATH,
            {},
            INVALID_STRUCTURE,
            id="bans-no-players",
        ),
        pytest.param(
            lambda steam: steam.users.resolve_vanity_url("robinwalker"),
            VANITY_PATH,
            {},
            INVALID_STRUCTURE,
            id="vanity-no-response",
        ),
        pytest.param(
            lambda steam: steam.users.resolve_vanity_url("robinwalker"),
            VANITY_PATH,
            {"response": {"steamid": STEAMID}},
            "Failed to resolve vanity URL",
            id="vanity-no-success",
        ),
        pytest.param(
            lambda steam: steam.users.get_user_group_list(STEAMID),
            GROUP_LIST_PATH,
            {"success": True, "groups": []},
            "Failed to get user group list",
            id="group-list-no-response",
        ),
        pytest.param(
            lambda steam: steam.users.get_user_group_list(STEAMID),
            GROUP_LIST_PATH,
            {"response": {"success": True, "groups": [{"id": "4"}]}},
            "Failed to get user group list",
            id="group-list-group-without-gid",
        ),
        pytest.param(
            lambda steam: steam.users.get_user_group_list(STEAMID),
            GROUP_LIST_PATH,
            {"response": {"success": True, "groups": {"gid": "4"}}},
            "Failed to get user group list",
            id="group-list-groups-not-a-list",
        ),
    ],
)
async def test_unexpected_body_is_raised_as_response_parsing_error(
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

    # Not a more specific error such as PrivateProfileError.
    assert type(excinfo.value) is ResponseParsingError
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
        pytest.param("76561200000000000", id="76561200000000000"),
        pytest.param(account(2**32 - 1), id="highest-account-id"),
    ],
)
async def test_valid_individual_steamid_is_sent(
    steam: Steam, fake_steam: FakeSteam, steamid: str
) -> None:
    fake_steam.api(
        "GET", SUMMARIES_PATH, json={"response": {"players": [player(steamid)]}}
    )

    summary = await steam.users.get_player_summary(steamid)

    assert summary is not None
    assert summary.steamid == steamid
    assert fake_steam.last.params["steamids"] == steamid


@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param(int(STEAMID), id="int"),
        pytest.param(SteamID(STEAMID), id="SteamID"),
    ],
)
async def test_steamid_accepts_int_and_steamid(
    steam: Steam, fake_steam: FakeSteam, steamid: int | SteamID
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=NO_PLAYERS)
    fake_steam.api("GET", FRIENDS_PATH, json=NO_FRIENDS)

    await steam.users.get_player_summaries([steamid, STEAMID])
    assert fake_steam.last.params["steamids"] == f"{STEAMID},{STEAMID}"

    await steam.users.get_friends_list(steamid)
    assert fake_steam.last.params["steamid"] == STEAMID


@pytest.mark.parametrize("bad_id", [True, int(STEAMID) + 2**32, 7.6e16, None])
async def test_non_steamid_values_are_rejected(
    steam: Steam, fake_steam: FakeSteam, bad_id: Any
) -> None:
    with pytest.raises(InvalidSteamIDError) as excinfo:
        await steam.users.get_player_summary(bad_id)

    assert excinfo.value.steamid == str(bad_id)
    assert fake_steam.requests == []


async def test_steamid_with_non_ascii_digit_is_rejected(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fullwidth_zero = "\N{FULLWIDTH DIGIT ZERO}"
    fake_steam.api("GET", SUMMARIES_PATH, json=NO_PLAYERS)

    with pytest.raises(InvalidSteamIDError):
        await steam.users.get_player_summary(STEAMID[:-1] + fullwidth_zero)

    assert fake_steam.requests == []


# -- batch size limit ----------------------------------------------------------


BATCH_CALLS = [
    pytest.param(
        lambda steam, ids: steam.users.get_player_summaries(ids),
        SUMMARIES_PATH,
        NO_PLAYERS,
        id="get_player_summaries",
    ),
    pytest.param(
        lambda steam, ids: steam.users.get_player_bans(ids),
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

    await steam.users.get_player_summaries(STEAMID)

    assert_sent_with_api_key(fake_steam.last, SUMMARIES_PATH)
    assert fake_steam.last.params == {"steamids": STEAMID, "key": API_KEY}


async def test_get_player_summaries_comma_joins_ids_in_order(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=load_fixture("player_summaries.json"))

    summaries = await steam.users.get_player_summaries(
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

    robin = (await steam.users.get_player_summaries([STEAMID, FRAG_MASTER, QUIET_ONE]))[
        0
    ]

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
        await steam.users.get_player_summaries([STEAMID, FRAG_MASTER, QUIET_ONE])
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
        await steam.users.get_player_summaries([STEAMID, FRAG_MASTER, QUIET_ONE])
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

    [summary] = await steam.users.get_player_summaries(STEAMID)

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

    [summary] = await steam.users.get_player_summaries(STEAMID)

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

    [summary] = await steam.users.get_player_summaries(STEAMID)

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

    summary = await steam.users.get_player_summary(STEAMID)

    assert isinstance(summary, PlayerSummary)
    assert summary.steamid == STEAMID
    assert summary.personaname == "Robin"
    assert_sent_with_api_key(fake_steam.last, SUMMARIES_PATH)
    assert fake_steam.last.params == {"steamids": STEAMID, "key": API_KEY}


async def test_get_player_summary_returns_none_for_unknown_account(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", SUMMARIES_PATH, json=NO_PLAYERS)

    assert await steam.users.get_player_summary(account(1_999_999_999)) is None


# -- GetFriendList -------------------------------------------------------------


async def test_get_friends_list_requests_friend_relationship_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json=NO_FRIENDS)

    await steam.users.get_friends_list(STEAMID)

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

    await steam.users.get_friends_list(STEAMID, relationship="all")

    assert fake_steam.last.params["relationship"] == "all"


async def test_get_friends_list_parses_friends(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json=load_fixture("player_friends.json"))

    friends = await steam.users.get_friends_list(STEAMID)

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

    friends = await steam.users.get_friends_list(STEAMID)

    assert friends[0].friend_since_datetime is None
    since = friends[2].friend_since_datetime
    assert since is not None
    assert since.timestamp() == 1258849452


async def test_get_friends_list_with_no_friends(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json=NO_FRIENDS)

    assert await steam.users.get_friends_list(STEAMID) == []


async def test_get_friends_list_without_friendslist_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", FRIENDS_PATH, json={})

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.users.get_friends_list(STEAMID)

    assert excinfo.value.steamid == STEAMID
    assert_sent_with_api_key(fake_steam.last, FRIENDS_PATH)


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
        await steam.users.get_friends_list(STEAMID)

    assert excinfo.value.steamid == STEAMID


# -- GetPlayerBans -------------------------------------------------------------


async def test_get_player_bans_sends_comma_joined_ids(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BANS_PATH, json=NO_BANS)

    assert await steam.users.get_player_bans([STEAMID, FRAG_MASTER]) == []

    assert_sent_with_api_key(fake_steam.last, BANS_PATH)
    assert fake_steam.last.params == {
        "steamids": f"{STEAMID},{FRAG_MASTER}",
        "key": API_KEY,
    }


async def test_get_player_bans_parses_real_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BANS_PATH, json=load_fixture("player_bans.json"))

    clean, banned = await steam.users.get_player_bans([STEAMID, FRAG_MASTER])

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

    assert await steam.users.resolve_vanity_url("robinwalker") == STEAMID

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

    assert await steam.users.resolve_vanity_url("no-such-profile-here") is None


async def test_resolve_vanity_url_passes_url_type(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", VANITY_PATH, json={"response": {"steamid": VALVE_GROUP, "success": 1}}
    )

    assert await steam.users.resolve_vanity_url("valve", url_type=2) == VALVE_GROUP

    assert fake_steam.last.params["url_type"] == "2"


@pytest.mark.parametrize(
    "url",
    [
        "https://steamcommunity.com/id/robinwalker",
        "http://steamcommunity.com/id/robinwalker",
        "steamcommunity.com/id/robinwalker",
        pytest.param(
            "https://steamcommunity.com/id/robinwalker/",
        ),
    ],
)
async def test_resolve_vanity_url_accepts_profile_url(
    steam: Steam, fake_steam: FakeSteam, url: str
) -> None:
    fake_steam.api("GET", VANITY_PATH, json=ROBIN_RESOLVED)

    steamid = await steam.users.resolve_vanity_url(url)

    assert fake_steam.last.params["vanityurl"] == "robinwalker"
    assert steamid == STEAMID


async def test_resolve_vanity_url_rejects_invalid_profiles_url(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(InvalidSteamIDError):
        await steam.users.resolve_vanity_url(
            "https://steamcommunity.com/profiles/12345/"
        )

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    "url",
    [
        f"https://steamcommunity.com/profiles/{STEAMID}",
        f"https://steamcommunity.com/profiles/{STEAMID}/",
    ],
)
async def test_resolve_vanity_url_returns_id_from_profiles_url_without_request(
    steam: Steam, fake_steam: FakeSteam, url: str
) -> None:
    assert await steam.users.resolve_vanity_url(url) == STEAMID
    assert fake_steam.requests == []


# -- IPlayerService/GetBadges and GetSteamLevel ----------------------------------

BADGES_PATH = "/IPlayerService/GetBadges/v1/"
LEVEL_PATH = "/IPlayerService/GetSteamLevel/v1/"
ROBIN_BADGES: dict[str, Any] = load_fixture("users_badges.json")
ROBIN_LEVEL: dict[str, Any] = {"response": {"player_level": 32}}
EMPTY_RESPONSE: dict[str, Any] = {"response": {}}

# Both take a Steam ID and send the API key, or the access token without one.
PLAYER_SERVICE_CALLS = [
    pytest.param(
        lambda steam, steamid: steam.users.get_badges(steamid),
        BADGES_PATH,
        ROBIN_BADGES,
        id="get_badges",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_steam_level(steamid),
        LEVEL_PATH,
        ROBIN_LEVEL,
        id="get_steam_level",
    ),
]


@pytest.mark.parametrize(("call", "path", "reply"), PLAYER_SERVICE_CALLS)
async def test_player_service_call_sends_steamid_and_api_key_over_get_v1(
    steam: Steam,
    fake_steam: FakeSteam,
    call: SteamIDCall,
    path: str,
    reply: dict[str, Any],
) -> None:
    fake_steam.api("GET", path, json=reply)

    await call(steam, STEAMID)

    assert len(fake_steam.requests) == 1
    assert_sent_with_api_key(fake_steam.last, path)
    assert fake_steam.last.params == {"steamid": STEAMID, "key": API_KEY}


@pytest.mark.parametrize(("call", "path", "reply"), PLAYER_SERVICE_CALLS)
async def test_player_service_call_sends_access_token_without_api_key(
    settings: Settings,
    fake_steam: FakeSteam,
    call: SteamIDCall,
    path: str,
    reply: dict[str, Any],
) -> None:
    fake_steam.api("GET", path, json=reply)

    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as steam:
        await call(steam, STEAMID)

    assert (fake_steam.last.method, fake_steam.last.path) == ("GET", path)
    assert fake_steam.last.params == {"steamid": STEAMID, "access_token": ACCESS_TOKEN}


@pytest.mark.parametrize(("call", "path", "reply"), PLAYER_SERVICE_CALLS)
async def test_player_service_call_without_credentials_raises_before_any_request(
    settings: Settings,
    fake_steam: FakeSteam,
    call: SteamIDCall,
    path: str,
    reply: dict[str, Any],
) -> None:
    fake_steam.api("GET", path, json=reply)

    async with Steam(settings=settings) as steam:
        with pytest.raises(
            SteamAPIError, match="An API key or access token is required"
        ) as excinfo:
            await call(steam, STEAMID)

    assert type(excinfo.value).__name__ == "AuthenticationError"
    assert fake_steam.requests == []


@pytest.mark.parametrize("bad_id", INVALID_STEAMIDS)
@pytest.mark.parametrize(("call", "path", "reply"), PLAYER_SERVICE_CALLS)
async def test_player_service_call_rejects_invalid_steamid_before_any_request(
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
        pytest.param(int(STEAMID), id="int"),
        pytest.param(SteamID(STEAMID), id="SteamID"),
    ],
)
@pytest.mark.parametrize(("call", "path", "reply"), PLAYER_SERVICE_CALLS)
async def test_player_service_call_accepts_int_and_steamid(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, Any], Awaitable[object]],
    path: str,
    reply: dict[str, Any],
    steamid: int | SteamID,
) -> None:
    fake_steam.api("GET", path, json=reply)

    await call(steam, steamid)

    assert fake_steam.last.params["steamid"] == STEAMID


@pytest.mark.parametrize(("call", "path", "reply"), PLAYER_SERVICE_CALLS)
async def test_player_service_http_error_is_raised_as_steam_api_error(
    steam: Steam,
    fake_steam: FakeSteam,
    call: SteamIDCall,
    path: str,
    reply: dict[str, Any],
) -> None:
    fake_steam.api("GET", path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await call(steam, STEAMID)

    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    ("call", "path", "body", "message"),
    [
        pytest.param(
            lambda steam: steam.users.get_badges(STEAMID),
            BADGES_PATH,
            {"response": {"badges": [{"badgeid": 13, "level": "max"}]}},
            "Failed to get badges",
            id="badges-non-numeric-level",
        ),
        pytest.param(
            lambda steam: steam.users.get_badges(STEAMID),
            BADGES_PATH,
            {"response": {"badges": {"badgeid": 13}}},
            "Failed to get badges",
            id="badges-not-a-list",
        ),
        pytest.param(
            lambda steam: steam.users.get_steam_level(STEAMID),
            LEVEL_PATH,
            {"response": {"player_level": "high"}},
            "Failed to get Steam level",
            id="level-non-numeric",
        ),
        pytest.param(
            lambda steam: steam.users.get_steam_level(STEAMID),
            LEVEL_PATH,
            {"response": [32]},
            "Failed to get Steam level",
            id="level-response-not-an-object",
        ),
    ],
)
async def test_player_service_malformed_body_raises_response_parsing_error(
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


async def test_get_badges_parses_badges_and_level_progress(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BADGES_PATH, json=ROBIN_BADGES)

    badges = await steam.users.get_badges(STEAMID)

    assert (
        badges.player_xp,
        badges.player_level,
        badges.player_xp_needed_to_level_up,
        badges.player_xp_needed_current_level,
    ) == (6950, 32, 250, 6800)
    assert [(b.badgeid, b.appid, b.level, b.xp) for b in badges.badges] == [
        (13, 0, 527, 777),
        (1, 0, 21, 1050),
        (1, 620, 5, 500),
        (1, 440, 1, 100),
    ]
    games_owned, _, portal2, tf2_foil = badges.badges
    assert games_owned.completion_time == 1727740800
    assert games_owned.scarcity == 1157430
    # Community badges have no community item or border.
    assert (games_owned.communityitemid, games_owned.border_color) == ("", 0)
    assert (portal2.communityitemid, portal2.border_color) == ("3917402871", 0)
    assert (tf2_foil.communityitemid, tf2_foil.border_color) == ("28376251827", 1)


async def test_get_badges_empty_response_gives_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BADGES_PATH, json=EMPTY_RESPONSE)

    badges = await steam.users.get_badges(STEAMID)

    assert badges.badges == []
    assert (
        badges.player_xp,
        badges.player_level,
        badges.player_xp_needed_to_level_up,
        badges.player_xp_needed_current_level,
    ) == (0, 0, 0, 0)


async def test_get_badges_badge_with_only_an_id_gives_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BADGES_PATH, json={"response": {"badges": [{"badgeid": 2}]}})

    [badge] = (await steam.users.get_badges(STEAMID)).badges

    assert badge.model_dump() == {
        "badgeid": 2,
        "level": 0,
        "completion_time": 0,
        "xp": 0,
        "scarcity": 0,
        "appid": 0,
        "communityitemid": "",
        "border_color": 0,
    }


async def test_get_steam_level_returns_player_level(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LEVEL_PATH, json=ROBIN_LEVEL)

    assert await steam.users.get_steam_level(STEAMID) == 32


async def test_get_steam_level_is_0_when_steam_leaves_it_out(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LEVEL_PATH, json=EMPTY_RESPONSE)

    assert await steam.users.get_steam_level(STEAMID) == 0


# -- ISteamUser/GetUserGroupList -------------------------------------------------

# A private profile gets HTTP 403 (as published clients report) with a JSON
# body; an invalid key gets HTTP 403 with this HTML page.
FORBIDDEN_HTML = (
    "<html><head><title>Forbidden</title></head><body><h1>Forbidden</h1>"
    "Access is denied. Retrying will not help. Please verify your "
    "<pre>key=</pre> parameter.</body></html>"
)


async def test_get_user_group_list_sends_steamid_and_api_key(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GROUP_LIST_PATH, json=GROUP_LIST)

    await steam.users.get_user_group_list(STEAMID)

    assert fake_steam.last.params == {"steamid": STEAMID, "key": API_KEY}


async def test_get_user_group_list_returns_group_ids_in_order(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GROUP_LIST_PATH, json=GROUP_LIST)

    gids = await steam.users.get_user_group_list(STEAMID)

    assert gids == [group["gid"] for group in GROUP_LIST["response"]["groups"]]
    assert gids[:2] == ["3284297", "5165781"]
    assert all(isinstance(gid, str) for gid in gids)


async def test_get_user_group_list_group_steamid_is_base_plus_gid(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    """The docstring's conversion: the Valve group (gid 4) is VALVE_GROUP."""
    fake_steam.api(
        "GET",
        GROUP_LIST_PATH,
        json={"response": {"success": True, "groups": [{"gid": "4"}]}},
    )

    [gid] = await steam.users.get_user_group_list(STEAMID)

    assert str(103582791429521408 + int(gid)) == VALVE_GROUP


async def test_get_user_group_list_without_groups_is_empty(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", GROUP_LIST_PATH, json={"response": {"success": True, "groups": []}}
    )

    assert await steam.users.get_user_group_list(STEAMID) == []


async def test_get_user_group_list_403_with_json_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        GROUP_LIST_PATH,
        status=403,
        json={"response": {"success": False, "error": "Private profile"}},
    )

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.users.get_user_group_list(STEAMID)

    assert excinfo.value.steamid == STEAMID
    assert API_KEY not in str(excinfo.value)
    assert API_KEY not in str(excinfo.value.__cause__)


async def test_get_user_group_list_403_html_invalid_key_stays_authentication_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        GROUP_LIST_PATH,
        status=403,
        text=FORBIDDEN_HTML,
        content_type="text/html",
    )

    with pytest.raises(AuthenticationError) as excinfo:
        await steam.users.get_user_group_list(STEAMID)

    assert not isinstance(excinfo.value, PrivateProfileError)
    assert excinfo.value.status_code == 403


@pytest.mark.parametrize(
    ("body", "message"),
    [
        pytest.param(
            {"response": {"success": False, "error": "Failed to get groups"}},
            "Failed to get user group list: Failed to get groups",
            id="error",
        ),
        pytest.param(
            {"response": {"success": False, "message": "No such user"}},
            "Failed to get user group list: No such user",
            id="message",
        ),
        pytest.param(
            {"response": {}},
            "Failed to get user group list: Steam answered success: false",
            id="empty-response",
        ),
    ],
)
async def test_get_user_group_list_success_false_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any], message: str
) -> None:
    fake_steam.api("GET", GROUP_LIST_PATH, json=body)

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.users.get_user_group_list(STEAMID)

    assert type(excinfo.value) is SteamAPIError
    assert str(excinfo.value) == message


@pytest.mark.parametrize(
    "response",
    [
        pytest.param({"success": False, "error": "Private profile"}, id="error"),
        pytest.param(
            {"success": False, "message": "Profile is not public"}, id="message"
        ),
    ],
)
async def test_get_user_group_list_success_false_private_raises_private_profile_error(
    steam: Steam, fake_steam: FakeSteam, response: dict[str, Any]
) -> None:
    """A 200 reply that says the profile is private maps like a 403 does."""
    fake_steam.api("GET", GROUP_LIST_PATH, json={"response": response})

    with pytest.raises(PrivateProfileError) as excinfo:
        await steam.users.get_user_group_list(STEAMID)

    assert excinfo.value.steamid == STEAMID
    assert API_KEY not in str(excinfo.value)


# -- IPlayerService: badge progress, link details, profile items, level ----------

BADGE_PROGRESS_PATH = "/IPlayerService/GetCommunityBadgeProgress/v1/"
LINK_DETAILS_PATH = "/IPlayerService/GetPlayerLinkDetails/v1/"
PROFILE_ITEMS_PATH = "/IPlayerService/GetProfileItemsEquipped/v1/"
LEVEL_DISTRIBUTION_PATH = "/IPlayerService/GetSteamLevelDistribution/v1/"

BADGE_PROGRESS: dict[str, Any] = load_fixture("users_community_badge_progress.json")
LINK_DETAILS: dict[str, Any] = load_fixture("users_player_link_details.json")
PROFILE_ITEMS: dict[str, Any] = load_fixture("users_profile_items_equipped.json")
LEVEL_DISTRIBUTION: dict[str, Any] = load_fixture("users_steam_level_distribution.json")

# Each method with the inputs it must send, and what an empty ``response``
# gives. All send the API key, or the access token without one.
PROFILE_SERVICE_CALLS = [
    pytest.param(
        lambda steam: steam.users.get_community_badge_progress(STEAMID, 2),
        BADGE_PROGRESS_PATH,
        BADGE_PROGRESS,
        {"steamid": STEAMID, "badgeid": "2"},
        [],
        id="get_community_badge_progress",
    ),
    pytest.param(
        lambda steam: steam.users.get_player_link_details([STEAMID, account(1)]),
        LINK_DETAILS_PATH,
        LINK_DETAILS,
        {"steamids[0]": STEAMID, "steamids[1]": account(1)},
        [],
        id="get_player_link_details",
    ),
    pytest.param(
        lambda steam: steam.users.get_profile_items_equipped(STEAMID),
        PROFILE_ITEMS_PATH,
        PROFILE_ITEMS,
        {"steamid": STEAMID},
        ProfileItemsEquipped(),
        id="get_profile_items_equipped",
    ),
    pytest.param(
        lambda steam: steam.users.get_steam_level_distribution(10),
        LEVEL_DISTRIBUTION_PATH,
        LEVEL_DISTRIBUTION,
        {"player_level": "10"},
        0.0,
        id="get_steam_level_distribution",
    ),
]

# The methods that take a Steam ID, called with ``steamid``.
PROFILE_STEAMID_CALLS = [
    pytest.param(
        lambda steam, steamid: steam.users.get_community_badge_progress(steamid),
        BADGE_PROGRESS_PATH,
        BADGE_PROGRESS,
        id="get_community_badge_progress",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_player_link_details(steamid),
        LINK_DETAILS_PATH,
        LINK_DETAILS,
        id="get_player_link_details",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_player_link_details([STEAMID, steamid]),
        LINK_DETAILS_PATH,
        LINK_DETAILS,
        id="get_player_link_details-list",
    ),
    pytest.param(
        lambda steam, steamid: steam.users.get_profile_items_equipped(steamid),
        PROFILE_ITEMS_PATH,
        PROFILE_ITEMS,
        id="get_profile_items_equipped",
    ),
]


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PROFILE_SERVICE_CALLS
)
async def test_profile_service_call_sends_inputs_and_api_key_over_get_v1(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
    inputs: dict[str, str],
    empty: object,
) -> None:
    fake_steam.api("GET", path, json=reply)

    await call(steam)

    assert len(fake_steam.requests) == 1
    assert_sent_with_api_key(fake_steam.last, path)
    assert fake_steam.last.params == {**inputs, "key": API_KEY}


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PROFILE_SERVICE_CALLS
)
async def test_profile_service_call_sends_access_token_without_api_key(
    settings: Settings,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
    inputs: dict[str, str],
    empty: object,
) -> None:
    fake_steam.api("GET", path, json=reply)

    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as steam:
        await call(steam)

    assert (fake_steam.last.method, fake_steam.last.path) == ("GET", path)
    assert fake_steam.last.params == {**inputs, "access_token": ACCESS_TOKEN}
    assert "Authorization" not in fake_steam.last.headers


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PROFILE_SERVICE_CALLS
)
async def test_profile_service_call_without_credentials_raises_before_any_request(
    settings: Settings,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
    inputs: dict[str, str],
    empty: object,
) -> None:
    fake_steam.api("GET", path, json=reply)

    async with Steam(settings=settings) as steam:
        with pytest.raises(
            AuthenticationError, match="An API key or access token is required"
        ):
            await call(steam)

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PROFILE_SERVICE_CALLS
)
async def test_profile_service_http_error_is_raised_as_steam_api_error(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
    inputs: dict[str, str],
    empty: object,
) -> None:
    fake_steam.api("GET", path, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await call(steam)

    assert excinfo.value.status_code == 500
    assert API_KEY not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PROFILE_SERVICE_CALLS
)
async def test_profile_service_empty_response_gives_defaults(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
    inputs: dict[str, str],
    empty: object,
) -> None:
    fake_steam.api("GET", path, json=EMPTY_RESPONSE)

    assert await call(steam) == empty


@pytest.mark.parametrize("bad_id", INVALID_STEAMIDS)
@pytest.mark.parametrize(("call", "path", "reply"), PROFILE_STEAMID_CALLS)
async def test_profile_service_call_rejects_invalid_steamid_before_any_request(
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
        pytest.param(int(STEAMID), id="int"),
        pytest.param(SteamID(STEAMID), id="SteamID"),
    ],
)
@pytest.mark.parametrize(("call", "path", "reply"), PROFILE_STEAMID_CALLS)
async def test_profile_service_call_accepts_int_and_steamid(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Callable[[Steam, Any], Awaitable[object]],
    path: str,
    reply: dict[str, Any],
    steamid: int | SteamID,
) -> None:
    fake_steam.api("GET", path, json=reply)

    await call(steam, steamid)

    sent = fake_steam.last.query
    assert STEAMID in (sent.getall("steamid", []) + sent.getall("steamids[0]", []))


@pytest.mark.parametrize(
    ("call", "path", "body", "message"),
    [
        pytest.param(
            lambda steam: steam.users.get_community_badge_progress(STEAMID),
            BADGE_PROGRESS_PATH,
            {"response": {"quests": [{"questid": "first"}]}},
            "Failed to get community badge progress",
            id="badge-progress-non-numeric-questid",
        ),
        pytest.param(
            lambda steam: steam.users.get_community_badge_progress(STEAMID),
            BADGE_PROGRESS_PATH,
            {"response": {"quests": {"questid": 101}}},
            "Failed to get community badge progress",
            id="badge-progress-quests-not-a-list",
        ),
        pytest.param(
            lambda steam: steam.users.get_player_link_details(STEAMID),
            LINK_DETAILS_PATH,
            {"response": {"accounts": [{"public_data": []}]}},
            "Failed to get player link details",
            id="link-details-public-data-not-an-object",
        ),
        pytest.param(
            lambda steam: steam.users.get_player_link_details(STEAMID),
            LINK_DETAILS_PATH,
            {"response": {"accounts": [{"private_data": {"time_created": "old"}}]}},
            "Failed to get player link details",
            id="link-details-non-numeric-time",
        ),
        pytest.param(
            lambda steam: steam.users.get_profile_items_equipped(STEAMID),
            PROFILE_ITEMS_PATH,
            {"response": {"avatar_frame": {"appid": "frame"}}},
            "Failed to get equipped profile items",
            id="profile-items-non-numeric-appid",
        ),
        pytest.param(
            lambda steam: steam.users.get_profile_items_equipped(STEAMID),
            PROFILE_ITEMS_PATH,
            {"response": {"profile_background": "none"}},
            "Failed to get equipped profile items",
            id="profile-items-slot-not-an-object",
        ),
        pytest.param(
            lambda steam: steam.users.get_steam_level_distribution(10),
            LEVEL_DISTRIBUTION_PATH,
            {"response": {"player_level_percentile": "top"}},
            "Failed to get Steam level distribution",
            id="level-distribution-not-a-number",
        ),
        pytest.param(
            lambda steam: steam.users.get_steam_level_distribution(10),
            LEVEL_DISTRIBUTION_PATH,
            {"response": [91.5]},
            "Failed to get Steam level distribution",
            id="level-distribution-response-not-an-object",
        ),
    ],
)
async def test_profile_service_malformed_body_raises_response_parsing_error(
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


# -- IPlayerService/GetCommunityBadgeProgress -------------------------------------


async def test_get_community_badge_progress_leaves_out_badgeid_when_none(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BADGE_PROGRESS_PATH, json=BADGE_PROGRESS)

    await steam.users.get_community_badge_progress(STEAMID)

    assert fake_steam.last.params == {"steamid": STEAMID, "key": API_KEY}


@pytest.mark.parametrize("badgeid", [0, -1, True, 2**31, "2", 2.0], ids=repr)
async def test_get_community_badge_progress_rejects_invalid_badgeid(
    steam: Steam, fake_steam: FakeSteam, badgeid: Any
) -> None:
    fake_steam.api("GET", BADGE_PROGRESS_PATH, json=BADGE_PROGRESS)

    with pytest.raises(ValueError, match="Invalid badge id"):
        await steam.users.get_community_badge_progress(STEAMID, badgeid)

    assert fake_steam.requests == []


async def test_get_community_badge_progress_parses_quests(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", BADGE_PROGRESS_PATH, json=BADGE_PROGRESS)

    quests = await steam.users.get_community_badge_progress(STEAMID, 2)

    assert all(isinstance(quest, CommunityBadgeQuest) for quest in quests)
    # Steam leaves ``completed`` out for quests not done yet.
    assert [(q.questid, q.completed) for q in quests] == [
        (101, True),
        (102, True),
        (103, False),
        (115, True),
        (121, False),
    ]


async def test_get_community_badge_progress_reads_explicit_false(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        BADGE_PROGRESS_PATH,
        json={"response": {"quests": [{"questid": 7, "completed": False}, {}]}},
    )

    quests = await steam.users.get_community_badge_progress(STEAMID, 2)

    assert quests == [
        CommunityBadgeQuest(questid=7, completed=False),
        CommunityBadgeQuest(),
    ]


# -- IPlayerService/GetPlayerLinkDetails ------------------------------------------


async def test_get_player_link_details_sends_one_id_as_steamids_0(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LINK_DETAILS_PATH, json=LINK_DETAILS)

    await steam.users.get_player_link_details(STEAMID)

    assert fake_steam.last.params == {"steamids[0]": STEAMID, "key": API_KEY}


async def test_get_player_link_details_keeps_id_order(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    ids = [account(3), STEAMID, account(1)]
    fake_steam.api("GET", LINK_DETAILS_PATH, json=LINK_DETAILS)

    await steam.users.get_player_link_details(iter(ids))

    assert fake_steam.last.params == {
        **{f"steamids[{n}]": steamid for n, steamid in enumerate(ids)},
        "key": API_KEY,
    }


async def test_get_player_link_details_without_ids_raises_before_request(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(ValueError, match="At least one Steam ID"):
        await steam.users.get_player_link_details([])

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    "bad_ids", [STEAMID.encode(), [STEAMID.encode()], [STEAMID, None]], ids=repr
)
async def test_get_player_link_details_rejects_non_steamid_values(
    steam: Steam, fake_steam: FakeSteam, bad_ids: Any
) -> None:
    with pytest.raises(InvalidSteamIDError):
        await steam.users.get_player_link_details(bad_ids)

    assert fake_steam.requests == []


async def test_get_player_link_details_parses_accounts(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LINK_DETAILS_PATH, json=LINK_DETAILS)

    robin, quiet = await steam.users.get_player_link_details([STEAMID, account(1)])

    assert isinstance(robin, PlayerLinkDetails)
    public = robin.public_data
    assert (public.steamid, public.persona_name, public.profile_url) == (
        STEAMID,
        "Robin",
        "robinwalker",
    )
    assert (public.visibility_state, public.profile_state) == (3, 1)
    assert public.content_country_restricted is False
    # Not sent, so 0.
    assert (public.privacy_state, public.ban_expires_time, public.account_flags) == (
        0,
        0,
        0,
    )
    assert public.sha_digest_avatar == "fTsMX71bLD5rPUoebyydCot+b1E="
    assert public.avatar_hash == "7d3b0c5fbd5b2c3e6b3d4a1e6f2c9d0a8b7e6f51"
    assert public.avatar_url == (
        "https://avatars.steamstatic.com/"
        "7d3b0c5fbd5b2c3e6b3d4a1e6f2c9d0a8b7e6f51_full.jpg"
    )
    private = robin.private_data
    assert (
        private.time_created,
        private.last_logoff_time,
        private.last_seen_online,
    ) == (1063407589, 1727737385, 1727740982)
    assert (private.persona_state, private.game_id, private.game_extra_info) == (
        0,
        "",
        "",
    )

    # A private profile: no custom URL, the default avatar, no presence data.
    assert quiet.public_data.visibility_state == 1
    assert quiet.public_data.profile_url == ""
    assert quiet.public_data.avatar_url == f"{DEFAULT_AVATAR}_full.jpg"
    assert quiet.private_data == PlayerLinkDetails().private_data


async def test_get_player_link_details_keeps_64_bit_ids_as_strings(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    non_steam_game = "17579876560805036032"
    fake_steam.api(
        "GET",
        LINK_DETAILS_PATH,
        json={
            "response": {
                "accounts": [
                    {
                        "public_data": {"steamid": STEAMID},
                        "private_data": {
                            "persona_state": 1,
                            "game_id": non_steam_game,
                            "game_extra_info": "Some Game",
                            "lobby_steam_id": "109775241058543776",
                        },
                    }
                ]
            }
        },
    )

    [details] = await steam.users.get_player_link_details(STEAMID)

    assert details.private_data.game_id == non_steam_game
    assert details.private_data.lobby_steam_id == "109775241058543776"
    assert details.private_data.persona_state == PersonaState.ONLINE


@pytest.mark.parametrize(
    "digest",
    [
        "",
        "not base64!",
        "é",
        # Valid base64, but not a 20-byte SHA-1: 1 byte, and the hex hash
        # itself (30 bytes once base64-decoded).
        "AQ==",
        "fef49e7fa7e1997310d705b2a6158ff8dc1cdfeb",
    ],
    ids=repr,
)
async def test_avatar_hash_is_empty_without_a_valid_digest(digest: str) -> None:
    public = PlayerLinkDetails.model_validate(
        {"public_data": {"sha_digest_avatar": digest}}
    ).public_data

    assert public.avatar_hash == ""
    assert public.avatar_url is None


def test_all_zero_avatar_digest_gives_the_default_avatar() -> None:
    """An all-zero SHA-1 means "no avatar set"; Steam shows its default one."""
    zero_digest = base64.b64encode(bytes(20)).decode()
    public = PlayerLinkDetails.model_validate(
        {"public_data": {"sha_digest_avatar": zero_digest}}
    ).public_data

    assert public.avatar_hash == "0" * 40
    assert public.avatar_url == f"{DEFAULT_AVATAR}_full.jpg"


# -- IPlayerService/GetProfileItemsEquipped ---------------------------------------


async def test_get_profile_items_equipped_sends_language(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PROFILE_ITEMS_PATH, json=PROFILE_ITEMS)

    await steam.users.get_profile_items_equipped(STEAMID, language="german")

    assert fake_steam.last.params == {
        "steamid": STEAMID,
        "language": "german",
        "key": API_KEY,
    }


async def test_get_profile_items_equipped_parses_items(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PROFILE_ITEMS_PATH, json=PROFILE_ITEMS)

    items = await steam.users.get_profile_items_equipped(STEAMID)

    assert isinstance(items, ProfileItemsEquipped)
    background = items.profile_background
    assert isinstance(background, ProfileItem)
    assert (
        background.communityitemid,
        background.appid,
        background.item_class,
        background.name,
    ) == ("28470941837", 1449850, 3, "Midnight Raid")
    assert background.movie_mp4.endswith(".mp4")
    assert background.movie_webm_small.endswith(".webm")
    assert background.image_small == ""

    frame = items.avatar_frame
    assert (frame.communityitemid, frame.item_class, frame.item_type) == (
        "32455405307",
        14,
        19,
    )
    assert frame.item_description == "Rewind the past, Control the future!"
    assert frame.image_small.startswith("items/1276800/")

    assert items.profile_modifier.profile_colors == [
        ProfileItemColor(
            style_name="backgroundgradient_left", color="rgba(175, 111, 37, 1)"
        ),
        ProfileItemColor(
            style_name="backgroundgradient_right", color="rgba(38, 72, 120, 1)"
        ),
    ]
    # Slots with nothing equipped are sent as {} and parse as empty items.
    assert items.mini_profile_background == ProfileItem()
    assert items.animated_avatar == ProfileItem()
    assert items.steam_deck_keyboard_skin == ProfileItem()


# -- IPlayerService/GetSteamLevelDistribution -------------------------------------


async def test_get_steam_level_distribution_returns_percentile(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LEVEL_DISTRIBUTION_PATH, json=LEVEL_DISTRIBUTION)

    percentile = await steam.users.get_steam_level_distribution(10)

    assert percentile == 91.59396362304688
    assert isinstance(percentile, float)


async def test_get_steam_level_distribution_accepts_level_0(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", LEVEL_DISTRIBUTION_PATH, json=LEVEL_DISTRIBUTION)

    await steam.users.get_steam_level_distribution(0)

    assert fake_steam.last.params == {"player_level": "0", "key": API_KEY}


@pytest.mark.parametrize("level", [-1, True, 2**32, "10", 10.0, None], ids=repr)
async def test_get_steam_level_distribution_rejects_invalid_level(
    steam: Steam, fake_steam: FakeSteam, level: Any
) -> None:
    fake_steam.api("GET", LEVEL_DISTRIBUTION_PATH, json=LEVEL_DISTRIBUTION)

    with pytest.raises(ValueError, match="Invalid player level"):
        await steam.users.get_steam_level_distribution(level)

    assert fake_steam.requests == []
