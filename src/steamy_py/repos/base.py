"""Base repository class for Steam API endpoints."""

import json
import logging
from collections.abc import Iterable, Mapping
from typing import Any

from ..client import Client
from ..exceptions import GameNotFoundError, PrivateProfileError, SteamAPIError

logger = logging.getLogger(__name__)


class BaseAPI:
    """Base class for all Steam API repositories."""

    def __init__(self, client: Client):
        """Initialize the base API repository.

        Args:
            client: Authenticated Steam API client
        """
        self.client = client

    @staticmethod
    def _indexed(name: str, values: Iterable[Any]) -> dict[str, str]:
        """Encode a repeated field the way the Web API expects it.

        Example:
            _indexed("appids_filter", [440, 620])
            -> {"appids_filter[0]": "440", "appids_filter[1]": "620"}
        """
        return {f"{name}[{index}]": str(value) for index, value in enumerate(values)}

    @staticmethod
    def _playerstats_body(error: SteamAPIError) -> dict[str, Any]:
        """Return the JSON body of an ISteamUserStats error, or re-raise.

        GetUserStatsForGame and GetPlayerAchievements answer a private
        profile with HTTP 403 and an app without stats with HTTP 400; the
        reason is in ``playerstats.error``. Errors without that body (an
        invalid key, an outage) are re-raised unchanged.
        """
        body = error.response_data if isinstance(error.response_data, dict) else {}
        playerstats = body.get("playerstats")
        if not isinstance(playerstats, dict) or not isinstance(
            playerstats.get("error"), str
        ):
            raise error
        return body

    @staticmethod
    def _raise_playerstats_error(message: str, steamid: str, app_id: int) -> None:
        """Raise the library exception for a ``playerstats.error`` message."""
        lowered = message.lower()
        if "private" in lowered or "not public" in lowered:
            raise PrivateProfileError(steamid)
        if (
            "no stats" in lowered
            or "not found" in lowered
            or "invalid appid" in lowered
        ):
            raise GameNotFoundError(str(app_id))
        raise SteamAPIError(f"Steam API error: {message}")

    def _build_url(self, interface: str, method: str, version: str = "v1") -> str:
        """Build Steam API URL.

        Args:
            interface: Steam API interface name (e.g., "ISteamUser")
            method: Method name (e.g., "GetPlayerSummaries")
            version: API version (default: "v1")

        Returns:
            Complete Steam API URL

        Example:
            _build_url("ISteamUser", "GetPlayerSummaries", "v2")
            -> "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
        """
        base_url = self.client.settings.STEAM_API_BASE_URL.rstrip("/")
        return f"{base_url}/{interface}/{method}/{version}/"

    def _build_store_url(self, endpoint: str) -> str:
        """Build Steam Store API URL.

        Args:
            endpoint: Store API endpoint

        Returns:
            Complete Steam Store API URL

        Example:
            _build_store_url("appdetails")
            -> "https://store.steampowered.com/api/appdetails"
        """
        base_url = self.client.settings.STEAM_STORE_BASE_URL.rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{base_url}/{endpoint}"

    async def _request(
        self,
        interface: str,
        method: str,
        version: str = "v1",
        params: dict[str, Any] | None = None,
        auth_type: str = "api_key",
        http_method: str = "GET",
        input_json: Mapping[str, Any] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to Steam API.

        Args:
            interface: Steam API interface name
            method: Method name
            version: API version
            params: Request parameters (query string for GET, form body for POST)
            auth_type: Authentication type ("api_key", "access_token", or "none")
            http_method: HTTP method ("GET", "POST", "PUT", "DELETE")
            input_json: Service-method input sent as a single ``input_json``
                parameter, for nested or repeated fields
            **kwargs: Additional request parameters

        Returns:
            JSON response data

        Raises:
            SteamAPIError: On any failure; see ``Client.request`` for the
                subclasses (AuthenticationError, RateLimitError,
                ServiceUnavailableError, NetworkError, ResponseParsingError)
        """
        url = self._build_url(interface, method, version)
        if input_json is not None:
            params = {
                **(params or {}),
                "input_json": json.dumps(input_json, separators=(",", ":")),
            }

        logger.debug(
            "Making %s request to %s/%s/%s with auth: %s",
            http_method,
            interface,
            method,
            version,
            auth_type,
        )

        return await self.client.request(
            http_method, url, params=params, auth_type=auth_type, **kwargs
        )

    async def _request_store(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
        auth_type: str = "none",
        http_method: str = "GET",
        **kwargs,
    ) -> dict[str, Any]:
        """Make request to Steam Store API.

        Args:
            endpoint: Store API endpoint
            params: Query parameters
            auth_type: Authentication type (defaults to "none" for store API)
            http_method: HTTP method ("GET", "POST", "PUT", "DELETE")
            **kwargs: Additional request parameters

        Returns:
            JSON response data

        Raises:
            SteamAPIError: On any failure; see ``Client.request`` for the
                subclasses (AuthenticationError, RateLimitError,
                ServiceUnavailableError, NetworkError, ResponseParsingError)
        """
        url = self._build_store_url(endpoint)

        logger.debug(
            "Making %s store request to %s with auth: %s",
            http_method,
            endpoint,
            auth_type,
        )

        return await self.client.request(
            http_method, url, params=params, auth_type=auth_type, **kwargs
        )

    # Convenience methods for common HTTP operations
    async def _get_request(
        self,
        interface: str,
        method: str,
        version: str = "v1",
        params: dict[str, Any] | None = None,
        auth_type: str = "api_key",
        **kwargs,
    ) -> dict[str, Any]:
        """Convenience method for GET requests."""
        return await self._request(
            interface, method, version, params, auth_type, "GET", **kwargs
        )

    async def _post_request(
        self,
        interface: str,
        method: str,
        version: str = "v1",
        params: dict[str, Any] | None = None,
        auth_type: str = "api_key",
        **kwargs,
    ) -> dict[str, Any]:
        """Convenience method for POST requests."""
        return await self._request(
            interface, method, version, params, auth_type, "POST", **kwargs
        )

    async def _put_request(
        self,
        interface: str,
        method: str,
        version: str = "v1",
        params: dict[str, Any] | None = None,
        auth_type: str = "api_key",
        **kwargs,
    ) -> dict[str, Any]:
        """Convenience method for PUT requests."""
        return await self._request(
            interface, method, version, params, auth_type, "PUT", **kwargs
        )

    async def _delete_request(
        self,
        interface: str,
        method: str,
        version: str = "v1",
        params: dict[str, Any] | None = None,
        auth_type: str = "api_key",
        **kwargs,
    ) -> dict[str, Any]:
        """Convenience method for DELETE requests."""
        return await self._request(
            interface, method, version, params, auth_type, "DELETE", **kwargs
        )
