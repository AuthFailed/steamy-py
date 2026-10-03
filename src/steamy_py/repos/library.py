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
