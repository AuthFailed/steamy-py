"""Models for IFriendsListService responses.

Service methods leave out every field Steam has no value for, so every field
has a default. Steam IDs (fixed64) arrive as strings and are kept as strings.
"""

from enum import IntEnum

from pydantic import Field

from ..exceptions import InvalidSteamIDError
from ..steamid import validate_steam_id
from .base import SteamModel


class EFriendRelationship(IntEnum):
    """Relationship of another user to the signed-in user."""

    NONE = 0
    BLOCKED = 1
    REQUEST_RECIPIENT = 2  # they sent the user a friend request
    FRIEND = 3
    REQUEST_INITIATOR = 4  # the user sent them a friend request
    IGNORED = 5
    IGNORED_FRIEND = 6
    SUGGESTED_FRIEND = 7  # no longer used by Steam


class FriendsListEntry(SteamModel):
    """One entry of the friends list (``CMsgClientFriendsList.Friend``)."""

    ulfriendid: str = Field(default="", description="SteamID64 of a user or group")
    efriendrelationship: int = Field(
        default=0,
        description="EFriendRelationship for a user, EClanRelationship for a group",
    )

    @property
    def is_user(self) -> bool:
        """Whether the entry is an individual account, not a Steam group."""
        try:
            validate_steam_id(self.ulfriendid)
        except InvalidSteamIDError:
            return False
        return True

    @property
    def is_friend(self) -> bool:
        """Whether the entry is a friend: a user with relationship FRIEND (3)."""
        return self.is_user and self.efriendrelationship == EFriendRelationship.FRIEND


class FriendsList(SteamModel):
    """The signed-in user's friends list (``CMsgClientFriendsList``).

    Besides friends, it holds pending friend requests and blocked or ignored
    users. It is the Steam client's friends list, which can also carry the
    user's Steam groups; a group's ``efriendrelationship`` is an
    EClanRelationship (3 is "member"), so use ``FriendsListEntry.is_friend``
    or ``friend_steamids`` to find friends.
    """

    bincremental: bool = Field(
        default=False, description="Whether this is a change set, not the full list"
    )
    friends: list[FriendsListEntry] = Field(default_factory=list)
    max_friend_count: int = Field(
        default=0, description="How many friends the user may have"
    )
    active_friend_count: int = Field(default=0, description="Number of active friends")
    friends_limit_hit: bool = Field(
        default=False, description="Whether the user has hit the friend limit"
    )

    @property
    def friend_steamids(self) -> list[str]:
        """SteamID64s of the friends (users with relationship FRIEND)."""
        return [entry.ulfriendid for entry in self.friends if entry.is_friend]


class GetFriendsListResult(SteamModel):
    """Body of ``CFriendsList_GetFriendsList_Response``."""

    friendslist: FriendsList = Field(default_factory=FriendsList)


class GetFriendsListResponse(SteamModel):
    """Response wrapper for IFriendsListService/GetFriendsList."""

    response: GetFriendsListResult = Field(default_factory=GetFriendsListResult)
