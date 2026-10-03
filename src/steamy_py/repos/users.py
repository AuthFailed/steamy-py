"""User endpoints (steam.users): ISteamUser and IPlayerService profile data."""

import logging
from collections.abc import Iterable

from ..exceptions import (
    AuthenticationError,
    PrivateProfileError,
    ResponseParsingError,
)
from ..models.player import (
    BadgesResponse,
    Friend,
    FriendsListResponse,
    PlayerBadges,
    PlayerBan,
    PlayerBansResponse,
    PlayerSummariesResponse,
    PlayerSummary,
    ResolveVanityURLResponse,
    SteamLevelResponse,
)
from ..steamid import SteamIDLike, validate_steam_id
from .base import BaseAPI

logger = logging.getLogger(__name__)


class UsersAPI(BaseAPI):
    """Steam users: profiles, friends, bans, vanity URLs and badges."""

    async def get_player_summaries(
        self, steam_ids: SteamIDLike | Iterable[SteamIDLike]
    ) -> list[PlayerSummary]:
        """Get player summary information for one or more Steam IDs.

        Args:
            steam_ids: One Steam ID or up to 100 (int, str or SteamID)

        Returns:
            List of player summaries

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            SteamAPIError: On API errors
        """
        steamids_param = ",".join(self._validate_steam_ids(steam_ids))

        with self._errors("get player summaries"):
            response_data = await self._request(
                interface="ISteamUser",
                method="GetPlayerSummaries",
                version="v2",
                params={"steamids": steamids_param},
            )

            # Parse the nested response structure
            if "response" not in response_data:
                raise ResponseParsingError("Invalid response structure from Steam API")

            response_obj = PlayerSummariesResponse.model_validate(
                response_data["response"]
            )
            return response_obj.players

    async def get_friends_list(
        self, steamid: SteamIDLike, relationship: str = "friend"
    ) -> list[Friend]:
        """Get friends list for a Steam user.

        Args:
            steamid: Steam ID of the user
            relationship: Relationship type (default: "friend")

        Returns:
            List of friends

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            PrivateProfileError: If profile is private
            PlayerNotFoundError: If player not found
            SteamAPIError: On API errors
        """
        steamid = validate_steam_id(steamid)

        try:
            response_data = await self._request(
                interface="ISteamUser",
                method="GetFriendList",
                version="v1",
                params={"steamid": steamid, "relationship": relationship},
            )
        except AuthenticationError as e:
            # GetFriendList answers HTTP 401 for a friends list that is not
            # public; an invalid key is HTTP 403.
            if e.status_code == 401:
                raise PrivateProfileError(steamid) from e
            raise

        with self._errors("get friends list"):
            if "friendslist" not in response_data:
                # This usually means the profile is private
                raise PrivateProfileError(steamid)

            response_obj = FriendsListResponse(
                friends=response_data["friendslist"].get("friends", [])
            )
            return response_obj.friends

    async def get_player_bans(
        self, steam_ids: SteamIDLike | Iterable[SteamIDLike]
    ) -> list[PlayerBan]:
        """Get ban information for one or more Steam users.

        Args:
            steam_ids: One Steam ID or up to 100 (int, str or SteamID)

        Returns:
            List of player ban information

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            SteamAPIError: On API errors
        """
        steamids_param = ",".join(self._validate_steam_ids(steam_ids))

        with self._errors("get player bans"):
            response_data = await self._request(
                interface="ISteamUser",
                method="GetPlayerBans",
                version="v1",
                params={"steamids": steamids_param},
            )

            if "players" not in response_data:
                raise ResponseParsingError("Invalid response structure from Steam API")

            response_obj = PlayerBansResponse(players=response_data["players"])
            return response_obj.players

    async def resolve_vanity_url(
        self, vanity_url: str, url_type: int = 1
    ) -> str | None:
        """Resolve a Steam vanity URL to a Steam ID.

        Args:
            vanity_url: The vanity name, or a full profile URL such as
                ``https://steamcommunity.com/id/<name>/``. For a
                ``/profiles/<steamid>`` URL the Steam ID is returned without
                a request.
            url_type: URL type (1=individual profile, 2=group,
                3=official game group)

        Returns:
            Steam ID if successful, None if not found

        Raises:
            InvalidSteamIDError: If a ``/profiles/`` URL holds an invalid ID
            SteamAPIError: On API errors
        """
        # Accept a full profile URL as well as the bare vanity name.
        if "/" in vanity_url:
            parts = [part for part in vanity_url.split("/") if part]
            if len(parts) >= 2 and parts[-2] == "profiles":
                return validate_steam_id(parts[-1])
            if len(parts) >= 2 and parts[-2] == "gid":
                return parts[-1]
            vanity_url = parts[-1] if parts else ""

        with self._errors("resolve vanity URL"):
            response_data = await self._request(
                interface="ISteamUser",
                method="ResolveVanityURL",
                version="v1",
                params={"vanityurl": vanity_url, "url_type": url_type},
            )

            if "response" not in response_data:
                raise ResponseParsingError("Invalid response structure from Steam API")

            response_obj = ResolveVanityURLResponse(response=response_data["response"])

            if response_obj.response.is_success:
                return response_obj.response.steamid
            else:
                return None

    async def get_player_summary(self, steamid: SteamIDLike) -> PlayerSummary | None:
        """Get single player summary (convenience method).

        Args:
            steamid: Steam ID of the player

        Returns:
            Player summary or None if not found

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            SteamAPIError: On API errors
        """
        summaries = await self.get_player_summaries(steamid)
        return summaries[0] if summaries else None

    @staticmethod
    def _validate_steam_ids(
        steam_ids: SteamIDLike | Iterable[SteamIDLike],
    ) -> list[str]:
        """Validate one Steam ID or a batch of up to 100.

        Raises:
            InvalidSteamIDError: If a Steam ID is invalid
            ValueError: If more than 100 Steam IDs are given
        """
        if isinstance(steam_ids, str) or not isinstance(steam_ids, Iterable):
            steam_ids = [steam_ids]
        steamids = [validate_steam_id(steamid) for steamid in steam_ids]
        if len(steamids) > 100:
            raise ValueError("Maximum 100 Steam IDs allowed per request")
        return steamids

    async def get_badges(self, steamid: SteamIDLike) -> PlayerBadges:
        """Get a user's badges and Steam level progress (IPlayerService/GetBadges).

        Sends the API key, or the access token when no key is set. Steam
        leaves out what it does not share (e.g. for a private profile), and
        those fields keep their defaults.

        Args:
            steamid: Steam ID of the user

        Returns:
            The badges, with the user's XP and level

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            AuthenticationError: If neither an API key nor an access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            "IPlayerService",
            "GetBadges",
            "get badges",
            {"steamid": validate_steam_id(steamid)},
            model=BadgesResponse,
            auth_type="any",
        )
        return response.response

    async def get_steam_level(self, steamid: SteamIDLike) -> int:
        """Get a user's Steam level (IPlayerService/GetSteamLevel).

        Sends the API key, or the access token when no key is set.

        Args:
            steamid: Steam ID of the user

        Returns:
            The Steam level; 0 when Steam leaves it out (e.g. for a private
            profile)

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            AuthenticationError: If neither an API key nor an access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            "IPlayerService",
            "GetSteamLevel",
            "get Steam level",
            {"steamid": validate_steam_id(steamid)},
            model=SteamLevelResponse,
            auth_type="any",
        )
        return response.response.player_level
