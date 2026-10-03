"""Utility endpoints (steam.util)."""

from ..models.util import ServerInfo, SupportedAPIList, SupportedAPIListResponse
from .base import BaseAPI

_INTERFACE = "ISteamWebAPIUtil"


class UtilAPI(BaseAPI):
    """Web API information (ISteamWebAPIUtil).

    These methods need no credential and never send one.
    """

    async def get_server_info(self) -> ServerInfo:
        """Get the Web API server's current time.

        Calls ISteamWebAPIUtil/GetServerInfo without a credential.

        Returns:
            The server time as a Unix timestamp and as text

        Raises:
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        return await self._call_service(
            _INTERFACE,
            "GetServerInfo",
            "get server info",
            model=ServerInfo,
            auth_type="none",
        )

    async def get_supported_api_list(self) -> SupportedAPIList:
        """List the Web API interfaces and methods Steam documents.

        Calls ISteamWebAPIUtil/GetSupportedAPIList without a credential.
        Steam lists its publicly documented interfaces, including methods
        that need a key to call; undocumented service methods are not
        listed. Each method version comes with its HTTP verb and parameters.

        Returns:
            The listed interfaces, with one method entry per version

        Raises:
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        response = await self._call_service(
            _INTERFACE,
            "GetSupportedAPIList",
            "get supported API list",
            model=SupportedAPIListResponse,
            auth_type="none",
        )
        return response.apilist
