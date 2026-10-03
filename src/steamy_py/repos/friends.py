"""Friends endpoints (steam.friends): the signed-in user's friends."""

from ..models.friends import FriendsList, GetFriendsListResponse
from .base import BaseAPI


class FriendsAPI(BaseAPI):
    """The signed-in user's friends (IFriendsListService)."""

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
