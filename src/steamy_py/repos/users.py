"""User endpoints (steam.users): ISteamUser and IPlayerService profile data."""

import logging
from collections.abc import Iterable
from typing import cast

from ..exceptions import (
    AuthenticationError,
    PrivateProfileError,
    ResponseParsingError,
    SteamAPIError,
)
from ..models.player import (
    BadgesResponse,
    CommunityBadgeProgressResponse,
    CommunityBadgeQuest,
    Friend,
    FriendsListResponse,
    PlayerBadges,
    PlayerBan,
    PlayerBansResponse,
    PlayerLinkDetails,
    PlayerLinkDetailsResponse,
    PlayerSummariesResponse,
    PlayerSummary,
    ProfileItemsEquipped,
    ProfileItemsEquippedResponse,
    ResolveVanityURLResponse,
    SteamLevelDistributionResponse,
    SteamLevelResponse,
    UserGroupListResponse,
)
from ..steamid import SteamID, SteamIDLike, validate_steam_id
from .base import BaseAPI

logger = logging.getLogger(__name__)

_INT32_MAX = 2**31 - 1
_UINT32_MAX = 2**32 - 1


def _checked_int(value: object, what: str, minimum: int, maximum: int) -> int:
    """Check that ``value`` is an int (not a ``bool``) in [minimum, maximum]."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ValueError(f"Invalid {what}: {value!r}")
    return int(value)


def _steam_id_list(steam_ids: SteamIDLike | Iterable[SteamIDLike]) -> list[str]:
    """Validate one Steam ID or several (at least one); a str is one ID, and
    bytes are rejected rather than read as a sequence of ints."""
    single = isinstance(steam_ids, str | bytes | SteamID) or not isinstance(
        steam_ids, Iterable
    )
    # validate_steam_id rejects anything that is not SteamIDLike (e.g. bytes).
    values = cast("Iterable[SteamIDLike]", [steam_ids] if single else steam_ids)
    ids = [validate_steam_id(steamid) for steamid in values]
    if not ids:
        raise ValueError("At least one Steam ID must be provided")
    return ids


class UsersAPI(BaseAPI):
    """Steam users: profiles, friends, bans, groups, vanity URLs, badges and levels."""

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

    async def get_community_badge_progress(
        self, steamid: SteamIDLike, badgeid: int | None = None
    ) -> list[CommunityBadgeQuest]:
        """Get the quests of a community badge and which ones a user completed.

        Calls IPlayerService/GetCommunityBadgeProgress with the API key, or
        the access token when no key is set.

        Args:
            steamid: Steam ID of the user
            badgeid: The badge to ask about; when None it is left out and
                Steam picks (published clients that leave it out get the
                quests of the community badge back; unverified which badge
                Steam uses)

        Returns:
            The badge's quests, each with ``completed``; empty when Steam
            sends none (e.g. for a badge without quests)

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            ValueError: If ``badgeid`` is not a positive 32-bit int
            AuthenticationError: If neither an API key nor an access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        steamid = validate_steam_id(steamid)
        if badgeid is not None:
            badgeid = _checked_int(badgeid, "badge id", 1, _INT32_MAX)
        response = await self._call_service(
            "IPlayerService",
            "GetCommunityBadgeProgress",
            "get community badge progress",
            {"steamid": steamid, "badgeid": badgeid},
            model=CommunityBadgeProgressResponse,
            auth_type="any",
        )
        return response.response.quests

    async def get_player_link_details(
        self, steamids: SteamIDLike | Iterable[SteamIDLike]
    ) -> list[PlayerLinkDetails]:
        """Get profile and presence data for one or more users.

        Calls IPlayerService/GetPlayerLinkDetails with the API key, or the
        access token when no key is set (Steam's method metadata allows
        either, as for GetOwnedGames; published clients use the API key, so
        the token is unverified). The ids are sent as ``steamids[0]``,
        ``steamids[1]``, ...; Steam's limit on how many one request may hold
        is not documented.

        ``public_data`` holds the persona name, visibility and avatar digest
        (``avatar_hash`` and ``avatar_url`` decode it). Which
        ``private_data`` fields Steam fills depends on the caller (unverified
        which); published clients that use an API key read only
        ``time_created``, ``last_logoff_time`` and ``last_seen_online``.

        Args:
            steamids: One Steam ID or several (int, str or SteamID)

        Returns:
            One entry per account Steam knows; match them by
            ``public_data.steamid``, since the order is not documented

        Raises:
            InvalidSteamIDError: If a Steam ID is invalid
            ValueError: If no Steam ID is given
            AuthenticationError: If neither an API key nor an access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            "IPlayerService",
            "GetPlayerLinkDetails",
            "get player link details",
            {"steamids": _steam_id_list(steamids)},
            model=PlayerLinkDetailsResponse,
            auth_type="any",
        )
        return response.response.accounts

    async def get_profile_items_equipped(
        self, steamid: SteamIDLike, language: str | None = None
    ) -> ProfileItemsEquipped:
        """Get the profile items a user has equipped.

        Calls IPlayerService/GetProfileItemsEquipped with the API key, or the
        access token when no key is set (published clients call it with an
        API key; the token is unverified).

        Args:
            steamid: Steam ID of the user
            language: Language of item names and descriptions, e.g.
                "english"; Steam's default when None

        Returns:
            The profile background, mini-profile background, avatar frame,
            animated avatar, profile modifier and Steam Deck keyboard skin; a
            slot with nothing equipped is an empty ``ProfileItem``

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            AuthenticationError: If neither an API key nor an access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            "IPlayerService",
            "GetProfileItemsEquipped",
            "get equipped profile items",
            {"steamid": validate_steam_id(steamid), "language": language},
            model=ProfileItemsEquippedResponse,
            auth_type="any",
        )
        return response.response

    async def get_steam_level_distribution(self, player_level: int) -> float:
        """Get how a Steam level compares with all Steam users.

        Calls IPlayerService/GetSteamLevelDistribution with the API key, or
        the access token when no key is set (published clients use either).
        The method is undocumented and no longer in Steam's published
        protobufs, so it may stop working (unverified that it still answers).

        Args:
            player_level: The Steam level to look up (0 or more)

        Returns:
            The level's percentile among Steam users (0 to 100; higher
            levels give higher percentiles, e.g. about 91.6 for level 10);
            0.0 when Steam leaves it out

        Raises:
            ValueError: If ``player_level`` is not an int from 0 to 2**32 - 1
            AuthenticationError: If neither an API key nor an access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        player_level = _checked_int(player_level, "player level", 0, _UINT32_MAX)
        response = await self._call_service(
            "IPlayerService",
            "GetSteamLevelDistribution",
            "get Steam level distribution",
            {"player_level": player_level},
            model=SteamLevelDistributionResponse,
            auth_type="any",
        )
        return response.response.player_level_percentile

    async def get_user_group_list(self, steamid: SteamIDLike) -> list[str]:
        """Get the Steam groups a user is a member of (ISteamUser/GetUserGroupList).

        Sends the API key only; like the other ISteamUser methods it never
        falls back to the access token.

        Steam returns each group as its 32-bit account id (``gid``), not as
        a group SteamID64; the SteamID64 of a group is
        ``103582791429521408 + int(gid)``.

        Args:
            steamid: Steam ID of the user

        Returns:
            The groups' account ids, as strings, in Steam's order

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            PrivateProfileError: If Steam answers HTTP 403 with a JSON body,
                or ``success: false`` with a reason that says the profile is
                private or not public; published clients see HTTP 403 for a
                private profile (the body is unverified), while an invalid
                key gets an HTML page
            AuthenticationError: If no API key is set, or Steam rejects it
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: If Steam answers ``success: false`` for another
                reason, or on other API errors
        """
        steamid = validate_steam_id(steamid)
        try:
            data = await self._request(
                "ISteamUser",
                "GetUserGroupList",
                "v1",
                params={"steamid": steamid},
                auth_type="api_key",
            )
        except AuthenticationError as e:
            if e.status_code == 403 and isinstance(e.response_data, dict):
                raise PrivateProfileError(steamid) from e
            raise

        with self._errors("get user group list"):
            result = UserGroupListResponse.model_validate(data).response
        if not result.success:
            reason = result.error or result.message or "Steam answered success: false"
            lowered = reason.lower()
            if "private" in lowered or "not public" in lowered:
                raise PrivateProfileError(steamid)
            raise SteamAPIError(f"Failed to get user group list: {reason}")
        return [group.gid for group in result.groups]
