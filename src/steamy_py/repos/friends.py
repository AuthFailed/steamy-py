"""Friends endpoints (steam.friends): the signed-in user's friends, their
nicknames and what they play."""

from ..models.friends import (
    FriendsGameplay,
    FriendsGameplayInfoResponse,
    FriendsList,
    GetFriendsListResponse,
    NicknameListResponse,
    PlayerNickname,
)
from ..steamid import validate_app_id
from .base import BaseAPI


class FriendsAPI(BaseAPI):
    """The signed-in user's friends (IFriendsListService, IPlayerService)."""

    async def get_friends_list(self) -> FriendsList:
        """Get the signed-in user's friends list (IFriendsListService/GetFriendsList).

        Calls Steam with the access token; the user is the token's owner. The
        list also holds pending friend requests and blocked or ignored
        accounts; ``FriendsList.friend_steamids`` keeps only the friends.

        Returns:
            The friends list, with the friend limit and count

        Raises:
            AuthenticationError: If no access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            "IFriendsListService",
            "GetFriendsList",
            "get friends list",
            model=GetFriendsListResponse,
            auth_type="access_token",
        )
        return response.response.friendslist

    async def get_friends_gameplay_info(
        self, appid: int, *, include_family_licenses: bool = False
    ) -> FriendsGameplay:
        """Get which friends play, played, own or want a game.

        Calls IPlayerService/GetFriendsGameplayInfo with the access token;
        the friends are those of the token's owner, who also gets
        ``your_info`` (own playtime, ownership and wishlist state).

        Args:
            appid: App ID of the game
            include_family_licenses: Also count games shared through Steam
                Family as owned (sent only when True; unverified effect)

        Returns:
            The friends per list (``in_game``, ``played_recently``,
            ``played_ever``, ``owns``, ``in_wishlist``) and ``your_info``;
            Steam fills only the playtimes it has, so entries in ``owns``
            and ``in_wishlist`` may hold just a Steam ID

        Raises:
            InvalidAppIDError: If ``appid`` is invalid
            AuthenticationError: If no access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            "IPlayerService",
            "GetFriendsGameplayInfo",
            "get friends gameplay info",
            {
                "appid": validate_app_id(appid),
                "include_family_licenses": include_family_licenses or None,
            },
            model=FriendsGameplayInfoResponse,
            auth_type="access_token",
        )
        return response.response

    async def get_nickname_list(self) -> list[PlayerNickname]:
        """Get the nicknames the signed-in user gave other users.

        Calls IPlayerService/GetNicknameList with the access token. Users
        are given by 32-bit account id; ``PlayerNickname.steamid`` turns it
        into a SteamID64.

        Returns:
            The nicknames; empty when the user has set none

        Raises:
            AuthenticationError: If no access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            "IPlayerService",
            "GetNicknameList",
            "get nickname list",
            model=NicknameListResponse,
            auth_type="access_token",
        )
        return response.response.nicknames
