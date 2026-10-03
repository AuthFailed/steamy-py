"""Library endpoints (steam.library): the games a user owns and plays."""

import logging

from ..exceptions import (
    PrivateProfileError,
    ResponseParsingError,
)
from ..models.game import (
    GetOwnedGamesResponse,
    OwnedGame,
)
from ..models.library import (
    LastPlayedGame,
    LastPlayedTimesResponse,
    RecentlyPlayedGames,
    RecentlyPlayedGamesResponse,
)
from ..steamid import SteamIDLike, validate_steam_id
from .base import BaseAPI

logger = logging.getLogger(__name__)


class LibraryAPI(BaseAPI):
    """A user's game library: owned and recently played games."""

    async def get_owned_games(
        self,
        steamid: SteamIDLike,
        include_appinfo: bool = True,
        include_played_free_games: bool = False,
        appids_filter: list[int] | None = None,
        include_extended_appinfo: bool = False,
        include_free_sub: bool = False,
        skip_unvetted_apps: bool | None = None,
        include_family_licenses: bool = False,
        language: str | None = None,
    ) -> list[OwnedGame]:
        """Get games owned by a Steam user.

        Args:
            steamid: Steam ID of the user
            include_appinfo: Include game name and logo information
            include_played_free_games: Include free games that have been played
            appids_filter: Optional list of App IDs to filter results
            include_extended_appinfo: Include capsule, sort name and the
                has_workshop/market/dlc/leaderboards flags
            include_free_sub: Include games from free subscriptions
            skip_unvetted_apps: Skip apps that have not been vetted; Steam's
                default is used when None
            include_family_licenses: Include games shared through Steam Family
            language: Language for game names

        Returns:
            List of owned games

        Raises:
            InvalidSteamIDError: If Steam ID format is invalid
            PrivateProfileError: If the game details are not public
            SteamAPIError: On API errors
        """
        steamid = validate_steam_id(steamid)

        params = {
            "steamid": steamid,
            "include_appinfo": "1" if include_appinfo else "0",
            "include_played_free_games": "1" if include_played_free_games else "0",
        }

        optional = {
            "include_extended_appinfo": "1" if include_extended_appinfo else None,
            "include_free_sub": "1" if include_free_sub else None,
            "skip_unvetted_apps": (
                None if skip_unvetted_apps is None else str(int(skip_unvetted_apps))
            ),
            "include_family_licenses": "1" if include_family_licenses else None,
            "language": language,
        }
        params.update({k: v for k, v in optional.items() if v is not None})
        if appids_filter:
            params.update(self._indexed("appids_filter", appids_filter))

        with self._errors("get owned games"):
            response_data = await self._request(
                interface="IPlayerService",
                method="GetOwnedGames",
                version="v1",
                auth_type="any",
                params=params,
            )

            if "response" not in response_data:
                raise ResponseParsingError("Invalid response structure from Steam API")

            if not response_data["response"]:
                # Empty response usually means private profile
                raise PrivateProfileError(steamid)

            response_obj = GetOwnedGamesResponse.model_validate(response_data)
            return response_obj.response.games

    async def get_recently_played_games(
        self, steamid: SteamIDLike, count: int | None = None
    ) -> RecentlyPlayedGames:
        """Get the games a user played in the last two weeks.

        Calls IPlayerService/GetRecentlyPlayedGames with the API key, or the
        access token when no key is set.

        Args:
            steamid: Steam ID of the user
            count: Return at most this many games; all when None or 0

        Returns:
            The number of games played in the last two weeks and the games

        Raises:
            InvalidSteamIDError: If the Steam ID is invalid
            AuthenticationError: If neither an API key nor an access token is set
            PrivateProfileError: If the game details are not public (Steam
                answers ``{"response": {}}``, as for GetOwnedGames; a public
                profile gets ``total_count``, even when it is 0)
            ResponseParsingError: If the response does not fit the model or
                has no ``response`` object
            SteamAPIError: On other API errors
        """
        steamid = validate_steam_id(steamid)
        data = await self._call_service(
            "IPlayerService",
            "GetRecentlyPlayedGames",
            "get recently played games",
            {"steamid": steamid, "count": count},
            auth_type="any",
        )
        with self._errors("get recently played games"):
            recent = RecentlyPlayedGamesResponse.model_validate(data)
        # Like GetOwnedGames: without a response object, "private" and "no
        # recent games" cannot be told apart.
        if "response" not in data:
            raise ResponseParsingError(
                "Failed to get recently played games: no response object"
            )
        if data["response"] == {}:
            raise PrivateProfileError(steamid)
        return recent.response

    async def get_last_played_times(
        self, min_last_played: int | None = None
    ) -> list[LastPlayedGame]:
        """Get the signed-in user's playtimes and last-played times per game.

        Calls IPlayerService/ClientGetLastPlayedTimes with the access token;
        the user is the access token's owner.

        Args:
            min_last_played: Only games played after this Unix timestamp (the
                latest last-played time the caller already knows); all games
                when None

        Returns:
            Playtimes and first/last-played times per game, overall and per
            platform

        Raises:
            AuthenticationError: If no access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            "IPlayerService",
            "ClientGetLastPlayedTimes",
            "get last played times",
            {"min_last_played": min_last_played},
            model=LastPlayedTimesResponse,
            auth_type="access_token",
        )
        return response.response.games
