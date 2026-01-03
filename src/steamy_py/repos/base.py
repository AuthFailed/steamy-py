"""Base repository class for Steam API endpoints."""

import logging
from typing import Any

from ..client import Client

logger = logging.getLogger(__name__)


class BaseAPI:
    """Base class for all Steam API repositories."""

    def __init__(self, client: Client):
        """Initialize the base API repository.

        Args:
            client: Authenticated Steam API client
        """
        self.client = client

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
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to Steam API.

        Args:
            interface: Steam API interface name
            method: Method name
            version: API version
            params: Query parameters
            auth_type: Authentication type ("api_key", "access_token", or "none")
            http_method: HTTP method ("GET", "POST", "PUT", "DELETE")
            **kwargs: Additional request parameters

        Returns:
            JSON response data

        Raises:
            ClientError: On HTTP or API errors
        """
        url = self._build_url(interface, method, version)

        logger.debug(
            f"Making {http_method} request to {interface}/{method}/{version} with auth: {auth_type}"
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
            ClientError: On HTTP or API errors
        """
        url = self._build_store_url(endpoint)

        logger.debug(
            f"Making {http_method} store request to {endpoint} with auth: {auth_type}"
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
