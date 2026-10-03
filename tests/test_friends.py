"""Tests for ``steam.friends``: IFriendsListService, with the access token.

``steam.users.get_friends_list`` (ISteamUser/GetFriendList, any public
profile, API key) is tested in ``test_player.py``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
)
from steamy_py.models.friends import (
    EFriendRelationship,
    FriendsList,
    FriendsListEntry,
)
from tests.fakesteam import ACCESS_TOKEN, API_KEY, FakeSteam, load_fixture

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
