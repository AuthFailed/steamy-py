"""Tests for ``steam.friends``: the signed-in user's friends, with the access token.

- ``get_friends_list``: IFriendsListService/GetFriendsList
- ``get_friends_gameplay_info``: IPlayerService/GetFriendsGameplayInfo
- ``get_nickname_list``: IPlayerService/GetNicknameList

``steam.users.get_friends_list`` (ISteamUser/GetFriendList, any public
profile, API key) is tested in ``test_player.py``. friends_gameplay_info.json
and friends_nickname_list.json are built from Steam's protobufs, shaped like
the replies other clients publish; no recorded replies were found.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    InvalidAppIDError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
)
from steamy_py.models.friends import (
    EFriendRelationship,
    FriendsGameplay,
    FriendsGameplayInfo,
    FriendsList,
    FriendsListEntry,
    OwnGameplayInfo,
    PlayerNickname,
)
from tests.fakesteam import ACCESS_TOKEN, API_KEY, STEAMID, FakeSteam, load_fixture

PATH = "/IFriendsListService/GetFriendsList/v1/"
FRIENDS_LIST: dict[str, Any] = load_fixture("friends_friends_list.json")

FRIENDS = [
    "76561197960265731",
    "76561197960265738",
    "76561197960265740",
    "76561198012345678",
]
REQUEST_FROM = "76561198087654321"
REQUEST_TO = "76561198034567890"
BLOCKED = "76561198055501234"
VALVE_GROUP = "103582791429521412"


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


def friends_list(*entries: dict[str, Any]) -> dict[str, Any]:
    """A GetFriendsList reply holding ``entries``."""
    return {"response": {"friendslist": {"friends": list(entries)}}}


# -- request ---------------------------------------------------------------------


async def test_get_friends_list_is_one_get_to_v1_with_access_token_only(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=FRIENDS_LIST)

    await steam.friends.get_friends_list()

    assert [(r.method, r.path) for r in fake_steam.requests] == [("GET", PATH)]
    # No inputs; the client has an API key too, but only the token is sent.
    assert fake_steam.last.params == {"access_token": ACCESS_TOKEN}
    assert "Authorization" not in fake_steam.last.headers


async def test_get_friends_list_works_with_access_token_only(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=FRIENDS_LIST)

    friends = await token_only_steam.friends.get_friends_list()

    assert friends.friend_steamids == FRIENDS
    assert fake_steam.last.params == {"access_token": ACCESS_TOKEN}


async def test_get_friends_list_without_access_token_raises_before_request(
    key_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=FRIENDS_LIST)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await key_only_steam.friends.get_friends_list()

    assert fake_steam.requests == []


# -- response --------------------------------------------------------------------


async def test_get_friends_list_parses_friends_list(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=FRIENDS_LIST)

    friends = await steam.friends.get_friends_list()

    assert isinstance(friends, FriendsList)
    assert friends.bincremental is False
    assert (friends.max_friend_count, friends.active_friend_count) == (410, 4)
    assert friends.friends_limit_hit is False
    assert all(isinstance(entry, FriendsListEntry) for entry in friends.friends)
    assert [(e.ulfriendid, e.efriendrelationship) for e in friends.friends] == [
        *((steamid, EFriendRelationship.FRIEND) for steamid in FRIENDS),
        (REQUEST_FROM, EFriendRelationship.REQUEST_RECIPIENT),
        (REQUEST_TO, EFriendRelationship.REQUEST_INITIATOR),
        (BLOCKED, EFriendRelationship.BLOCKED),
    ]


async def test_friend_steamids_keeps_only_friends(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=FRIENDS_LIST)

    friends = await steam.friends.get_friends_list()

    assert friends.friend_steamids == FRIENDS
    assert [e.is_friend for e in friends.friends] == [True] * 4 + [False] * 3


async def test_steam_group_member_is_not_a_friend(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    """A group's relationship is an EClanRelationship, where 3 is "member"."""
    fake_steam.api(
        "GET",
        PATH,
        json=friends_list(
            {"ulfriendid": VALVE_GROUP, "efriendrelationship": 3},
            {"ulfriendid": FRIENDS[0], "efriendrelationship": 3},
        ),
    )

    group, friend = (await steam.friends.get_friends_list()).friends

    assert (group.is_user, group.is_friend) == (False, False)
    assert (friend.is_user, friend.is_friend) == (True, True)


async def test_unknown_relationship_is_kept_as_int(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        PATH,
        json=friends_list({"ulfriendid": FRIENDS[0], "efriendrelationship": 42}),
    )

    friends = await steam.friends.get_friends_list()

    assert friends.friends[0].efriendrelationship == 42
    assert friends.friend_steamids == []


async def test_get_friends_list_empty_response_gives_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json={"response": {}})

    friends = await steam.friends.get_friends_list()

    assert friends == FriendsList()
    assert friends.friends == []
    assert friends.friend_steamids == []
    assert (friends.max_friend_count, friends.active_friend_count) == (0, 0)
    assert (friends.bincremental, friends.friends_limit_hit) == (False, False)


async def test_entry_without_fields_gives_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=friends_list({}))

    [entry] = (await steam.friends.get_friends_list()).friends

    assert (entry.ulfriendid, entry.efriendrelationship) == ("", 0)
    assert (entry.is_user, entry.is_friend) == (False, False)


# -- errors ----------------------------------------------------------------------


async def test_http_error_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.friends.get_friends_list()

    assert excinfo.value.status_code == 500
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            friends_list({"ulfriendid": FRIENDS[0], "efriendrelationship": "friend"}),
            id="non-numeric-relationship",
        ),
        pytest.param(
            {"response": {"friendslist": {"friends": {"ulfriendid": FRIENDS[0]}}}},
            id="friends-not-a-list",
        ),
        pytest.param({"response": {"friendslist": []}}, id="friendslist-not-an-object"),
    ],
)
async def test_malformed_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.api("GET", PATH, json=body)

    with pytest.raises(ResponseParsingError, match="Failed to get friends list"):
        await steam.friends.get_friends_list()


# -- IPlayerService/GetFriendsGameplayInfo and GetNicknameList --------------------

GAMEPLAY_PATH = "/IPlayerService/GetFriendsGameplayInfo/v1/"
NICKNAME_PATH = "/IPlayerService/GetNicknameList/v1/"
GAMEPLAY: dict[str, Any] = load_fixture("friends_gameplay_info.json")
NICKNAMES: dict[str, Any] = load_fixture("friends_nickname_list.json")

INDIVIDUAL_BASE = 76561197960265728

Call = Callable[[Steam], Awaitable[object]]

# Each method with the inputs it must send, and what an empty ``response``
# gives. Both need the access token and never send the API key.
PLAYER_SERVICE_CALLS = [
    pytest.param(
        lambda steam: steam.friends.get_friends_gameplay_info(620),
        GAMEPLAY_PATH,
        GAMEPLAY,
        {"appid": "620"},
        FriendsGameplay(),
        id="get_friends_gameplay_info",
    ),
    pytest.param(
        lambda steam: steam.friends.get_nickname_list(),
        NICKNAME_PATH,
        NICKNAMES,
        {},
        [],
        id="get_nickname_list",
    ),
]


def account(account_id: int) -> str:
    """SteamID64 of the individual account with ``account_id``."""
    return str(INDIVIDUAL_BASE + account_id)


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PLAYER_SERVICE_CALLS
)
async def test_player_service_call_is_one_get_to_v1_with_access_token_only(
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

    assert [(r.method, r.path) for r in fake_steam.requests] == [("GET", path)]
    # The client has an API key too, but only the token is sent.
    assert fake_steam.last.params == {**inputs, "access_token": ACCESS_TOKEN}
    assert "Authorization" not in fake_steam.last.headers


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PLAYER_SERVICE_CALLS
)
async def test_player_service_call_works_with_access_token_only(
    token_only_steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
    inputs: dict[str, str],
    empty: object,
) -> None:
    fake_steam.api("GET", path, json=reply)

    await call(token_only_steam)

    assert fake_steam.last.params == {**inputs, "access_token": ACCESS_TOKEN}


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PLAYER_SERVICE_CALLS
)
async def test_player_service_call_without_access_token_raises_before_request(
    key_only_steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
    inputs: dict[str, str],
    empty: object,
) -> None:
    fake_steam.api("GET", path, json=reply)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await call(key_only_steam)

    assert fake_steam.requests == []


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PLAYER_SERVICE_CALLS
)
async def test_player_service_http_error_is_raised_as_steam_api_error(
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
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    ("call", "path", "reply", "inputs", "empty"), PLAYER_SERVICE_CALLS
)
async def test_player_service_empty_response_gives_defaults(
    steam: Steam,
    fake_steam: FakeSteam,
    call: Call,
    path: str,
    reply: dict[str, Any],
    inputs: dict[str, str],
    empty: object,
) -> None:
    fake_steam.api("GET", path, json={"response": {}})

    assert await call(steam) == empty


@pytest.mark.parametrize(
    ("call", "path", "body", "message"),
    [
        pytest.param(
            lambda steam: steam.friends.get_friends_gameplay_info(620),
            GAMEPLAY_PATH,
            {"response": {"owns": {"steamid": STEAMID}}},
            "Failed to get friends gameplay info",
            id="gameplay-owns-not-a-list",
        ),
        pytest.param(
            lambda steam: steam.friends.get_friends_gameplay_info(620),
            GAMEPLAY_PATH,
            {"response": {"played_ever": [{"minutes_played_forever": "lots"}]}},
            "Failed to get friends gameplay info",
            id="gameplay-non-numeric-minutes",
        ),
        pytest.param(
            lambda steam: steam.friends.get_friends_gameplay_info(620),
            GAMEPLAY_PATH,
            {"response": {"your_info": []}},
            "Failed to get friends gameplay info",
            id="gameplay-your-info-not-an-object",
        ),
        pytest.param(
            lambda steam: steam.friends.get_nickname_list(),
            NICKNAME_PATH,
            {"response": {"nicknames": [{"accountid": "gabe"}]}},
            "Failed to get nickname list",
            id="nickname-non-numeric-accountid",
        ),
        pytest.param(
            lambda steam: steam.friends.get_nickname_list(),
            NICKNAME_PATH,
            {"response": []},
            "Failed to get nickname list",
            id="nickname-response-not-an-object",
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


# -- GetFriendsGameplayInfo -------------------------------------------------------


async def test_get_friends_gameplay_info_sends_include_family_licenses(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GAMEPLAY_PATH, json=GAMEPLAY)

    await steam.friends.get_friends_gameplay_info(620, include_family_licenses=True)

    assert fake_steam.last.params == {
        "appid": "620",
        "include_family_licenses": "1",
        "access_token": ACCESS_TOKEN,
    }


@pytest.mark.parametrize("appid", [0, -1, True, "620", 2**32, None], ids=repr)
async def test_get_friends_gameplay_info_rejects_invalid_appid_before_request(
    steam: Steam, fake_steam: FakeSteam, appid: Any
) -> None:
    fake_steam.api("GET", GAMEPLAY_PATH, json=GAMEPLAY)

    with pytest.raises(InvalidAppIDError):
        await steam.friends.get_friends_gameplay_info(appid)

    assert fake_steam.requests == []


async def test_get_friends_gameplay_info_parses_lists(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", GAMEPLAY_PATH, json=GAMEPLAY)

    info = await steam.friends.get_friends_gameplay_info(620)

    assert isinstance(info, FriendsGameplay)
    assert info.your_info == OwnGameplayInfo(
        steamid=STEAMID,
        minutes_played=177,
        minutes_played_forever=5162,
        in_wishlist=False,
        owned=True,
    )
    assert info.in_game == [
        FriendsGameplayInfo(
            steamid=account(52079950), minutes_played=64, minutes_played_forever=2210
        )
    ]
    assert [(f.steamid, f.minutes_played) for f in info.played_recently] == [
        (account(52079950), 171),
        (account(74326593), 12),
    ]
    assert [(f.steamid, f.minutes_played_forever) for f in info.played_ever] == [
        (account(52079950), 2210),
        (account(74326593), 840),
        (account(127459565), 191),
    ]
    # Entries Steam sends with only a Steam ID keep 0 playtimes.
    assert [f.steamid for f in info.owns] == [
        account(52079950),
        account(74326593),
        account(127459565),
        account(94301162),
    ]
    assert all(
        (f.minutes_played, f.minutes_played_forever) == (0, 0) for f in info.owns
    )
    assert info.in_wishlist == [FriendsGameplayInfo(steamid=account(18233872))]


# -- GetNicknameList --------------------------------------------------------------


async def test_get_nickname_list_parses_nicknames(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", NICKNAME_PATH, json=NICKNAMES)

    nicknames = await steam.friends.get_nickname_list()

    assert all(isinstance(entry, PlayerNickname) for entry in nicknames)
    assert [(n.accountid, n.nickname) for n in nicknames] == [
        (52079950, "frag master"),
        (74326593, "Jess (work)"),
        (127459565, "好哥哥"),
    ]
    assert [n.steamid for n in nicknames] == [
        account(52079950),
        account(74326593),
        account(127459565),
    ]


@pytest.mark.parametrize("accountid", [0, 2**32], ids=repr)
async def test_nickname_steamid_is_none_for_invalid_account_id(accountid: int) -> None:
    assert PlayerNickname(accountid=accountid).steamid is None
