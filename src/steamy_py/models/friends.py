"""Models for IFriendsListService responses.

Service methods leave out every field Steam has no value for, so every field
has a default. Steam IDs (fixed64) arrive as strings and are kept as strings.
"""

from enum import IntEnum

from pydantic import Field

from ..exceptions import InvalidSteamIDError
from ..steamid import SteamID, validate_steam_id
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


# IPlayerService/GetFriendsGameplayInfo
class FriendsGameplayInfo(SteamModel):
    """A friend's playtime in one game.

    ``CPlayer_GetFriendsGameplayInfo_Response.FriendsGameplayInfo``; Steam's
    name, although each entry is one friend.
    """

    steamid: str = Field(default="", description="SteamID64 of the friend")
    minutes_played: int = Field(
        default=0, description="Recent playtime in minutes (when Steam sends it)"
    )
    minutes_played_forever: int = Field(
        default=0, description="Total playtime in minutes (when Steam sends it)"
    )


class OwnGameplayInfo(SteamModel):
    """The signed-in user's own playtime and ownership of the game.

    ``CPlayer_GetFriendsGameplayInfo_Response.OwnGameplayInfo``.
    """

    steamid: str = Field(default="", description="SteamID64 of the signed-in user")
    minutes_played: int = Field(default=0, description="Recent playtime in minutes")
    minutes_played_forever: int = Field(
        default=0, description="Total playtime in minutes"
    )
    in_wishlist: bool = Field(
        default=False, description="Whether the game is on the user's wishlist"
    )
    owned: bool = Field(default=False, description="Whether the user owns the game")


class FriendsGameplay(SteamModel):
    """Which friends play, played, own or want a game.

    Body of ``CPlayer_GetFriendsGameplayInfo_Response``. A friend can be in
    several lists (e.g. ``played_ever`` and ``owns``).
    """

    your_info: OwnGameplayInfo = Field(default_factory=OwnGameplayInfo)
    in_game: list[FriendsGameplayInfo] = Field(
        default_factory=list, description="Friends playing the game now"
    )
    played_recently: list[FriendsGameplayInfo] = Field(
        default_factory=list, description="Friends who played it recently"
    )
    played_ever: list[FriendsGameplayInfo] = Field(
        default_factory=list, description="Friends who have played it"
    )
    owns: list[FriendsGameplayInfo] = Field(
        default_factory=list, description="Friends who own it"
    )
    in_wishlist: list[FriendsGameplayInfo] = Field(
        default_factory=list, description="Friends with the game on their wishlist"
    )


class FriendsGameplayInfoResponse(SteamModel):
    """Response wrapper for IPlayerService/GetFriendsGameplayInfo."""

    response: FriendsGameplay = Field(default_factory=FriendsGameplay)


# IPlayerService/GetNicknameList
class PlayerNickname(SteamModel):
    """A nickname the signed-in user gave another user.

    ``CPlayer_GetNicknameList_Response.PlayerNickname``.
    """

    accountid: int = Field(default=0, description="32-bit account id of the user")
    nickname: str = Field(default="", description="The nickname")

    @property
    def steamid(self) -> str | None:
        """SteamID64 of the user, or None when ``accountid`` is not valid."""
        try:
            return str(SteamID.from_account_id(self.accountid))
        except InvalidSteamIDError:
            return None


class NicknameList(SteamModel):
    """Body of ``CPlayer_GetNicknameList_Response``."""

    nicknames: list[PlayerNickname] = Field(default_factory=list)


class NicknameListResponse(SteamModel):
    """Response wrapper for IPlayerService/GetNicknameList."""

    response: NicknameList = Field(default_factory=NicknameList)
