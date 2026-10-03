"""Game server endpoints (steam.servers)."""

from ..exceptions import GameNotFoundError
from ..models.servers import (
    GameServer,
    ServerListResponse,
    UpToDateCheck,
    UpToDateCheckResponse,
)
from ..steamid import validate_app_id
from .base import BaseAPI

_UINT32_MAX = 2**32 - 1


class ServersAPI(BaseAPI):
    """Game servers (IGameServersService, ISteamApps)."""

    async def get_server_list(
        self, filter: str | None = None, limit: int | None = None
    ) -> list[GameServer]:
        r"""List game servers that match a master server filter.

        Calls IGameServersService/GetServerList with the API key if the
        client has one, else the access token (whether Steam accepts an
        access token here is unverified; published clients send a key).

        ``filter`` uses the master server query syntax: ``\key\value`` pairs
        run together, all of which must match. Common keys (see "Master Server
        Query Protocol" on the Valve Developer Community wiki for the full
        list):

        - ``\appid\730``: servers of an app
        - ``\gamedir\tf``: servers running a game directory (mod)
        - ``\map\de_dust2``: servers on a map
        - ``\dedicated\1``, ``\secure\1`` (VAC), ``\linux\1``
        - ``\password\0``: servers without a password
        - ``\empty\1``: servers that are not empty; ``\noplayers\1``: servers
          that are empty
        - ``\full\1``: servers that are not full
        - ``\gameaddr\1.2.3.4``: servers at an address (port optional)
        - ``\name_match\*text*``: server names matching a pattern (``*`` is a
          wildcard)
        - ``\gametype\tag1,tag2``: servers with all of these tags
        - ``\nor\[n]``: leave out servers matching any of the next ``n``
          conditions; ``\nand\[n]``: those matching all of them

        Example: ``r"\appid\440\dedicated\1\empty\1"``.

        Args:
            filter: The filter; Steam's behaviour without one is unverified
            limit: Most servers to return; Steam's default is 100

        Returns:
            The matching servers

        Raises:
            ValueError: If ``filter`` is not a string or ``limit`` is not a
                positive int
            AuthenticationError: If the client has neither an API key nor an
                access token, or Steam rejects it
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        if filter is not None and not isinstance(filter, str):
            raise ValueError(f"filter must be a string, not {filter!r}")
        if limit is not None and (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 0 < limit <= _UINT32_MAX
        ):
            raise ValueError(f"limit must be a positive int, not {limit!r}")
        result = await self._call_service(
            "IGameServersService",
            "GetServerList",
            "get server list",
            {"filter": filter, "limit": limit},
            model=ServerListResponse,
            auth_type="any",
        )
        return result.response.servers

    async def up_to_date_check(self, appid: int, version: int) -> UpToDateCheck:
        """Check whether a game (server) version is the current one.

        Calls ISteamApps/UpToDateCheck without a credential.

        Args:
            appid: Steam App ID of the game
            version: The installed version, as the integer game servers
                report (e.g. ``PatchVersion`` in steam.inf, without dots)

        Returns:
            ``up_to_date``, ``version_is_listable``, and ``required_version``
            and ``message`` when the version is out of date

        Raises:
            InvalidAppIDError: If the App ID is invalid
            ValueError: If ``version`` is not a 32-bit unsigned int
            GameNotFoundError: If Steam has no version data for the app
                (``success`` false, e.g. "Couldn't get app info for the app
                specified.")
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        validate_app_id(appid)
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or not 0 <= version <= _UINT32_MAX
        ):
            raise ValueError(f"Invalid version: {version!r}")
        result = await self._call_service(
            "ISteamApps",
            "UpToDateCheck",
            "check app version",
            {"appid": appid, "version": version},
            model=UpToDateCheckResponse,
            auth_type="none",
        )
        check = result.response
        if not check.success:
            reason = check.error or "Steam gave no reason"
            raise GameNotFoundError(
                str(appid), f"No version data for app {appid}: {reason}"
            )
        return check
