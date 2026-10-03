"""Base repository class for Steam API endpoints."""

import json
import logging
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from typing import Any, TypeVar, overload

from pydantic import BaseModel, ValidationError

from ..client import Client
from ..exceptions import (
    GameNotFoundError,
    PrivateProfileError,
    ResponseParsingError,
    SteamAPIError,
)
from ..steamid import SteamID

ModelT = TypeVar("ModelT", bound=BaseModel)


logger = logging.getLogger(__name__)


def _scalar(value: Any) -> str:
    """Encode one input value as Steam expects it.

    Booleans become "1"/"0" and ints their decimal form; ``str()`` alone
    would give "EFamilyGroupRole.ADULT" for an enum member on Python 3.10.
    """
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, int):
        return str(int(value))
    return str(value)


class BaseAPI:
    """Base class for all Steam API repositories."""

    def __init__(self, client: Client):
        """Initialize the base API repository.

        Args:
            client: Authenticated Steam API client
        """
        self.client = client

    @staticmethod
    @contextmanager
    def _errors(operation: str) -> Iterator[None]:
        """Raise only library exceptions from the block.

        Library exceptions pass through unchanged, a response that does not
        fit its model raises ``ResponseParsingError``, and anything else
        ``SteamAPIError``; the message starts with "Failed to <operation>".
        """
        try:
            yield
        except SteamAPIError:
            raise
        except ValidationError as e:
            logger.debug("Failed to %s: %s", operation, e)
            raise ResponseParsingError(
                f"Failed to {operation}: unexpected response: {e}"
            ) from e
        except Exception as e:
            logger.debug("Failed to %s: %s", operation, e)
            raise SteamAPIError(f"Failed to {operation}: {e}") from e

    @classmethod
    def _service_inputs(cls, inputs: Mapping[str, Any]) -> dict[str, Any]:
        """Encode service-method inputs; ``None`` means "leave it out".

        Booleans become "1"/"0", other iterables ``name[0]``, ``name[1]``,
        ..., ints (including enum members) their decimal form, and a
        ``SteamID`` its SteamID64.
        """
        encoded: dict[str, Any] = {}
        for name, value in inputs.items():
            if value is None:
                continue
            if isinstance(value, SteamID):
                encoded[name] = str(value)
            elif isinstance(value, str | bytes):
                encoded[name] = value
            elif isinstance(value, Iterable) and not isinstance(value, Mapping):
                encoded.update(cls._indexed(name, value))
            else:
                encoded[name] = _scalar(value)
        return encoded

    @overload
    async def _call_service(
        self,
        interface: str,
        method: str,
        operation: str,
        inputs: Mapping[str, Any] | None = ...,
        *,
        model: type[ModelT],
        version: str = ...,
        http_method: str = ...,
        auth_type: str = ...,
    ) -> ModelT: ...

    @overload
    async def _call_service(
        self,
        interface: str,
        method: str,
        operation: str,
        inputs: Mapping[str, Any] | None = ...,
        *,
        model: None = ...,
        version: str = ...,
        http_method: str = ...,
        auth_type: str = ...,
    ) -> dict[str, Any]: ...

    async def _call_service(
        self,
        interface: str,
        method: str,
        operation: str,
        inputs: Mapping[str, Any] | None = None,
        *,
        model: type[BaseModel] | None = None,
        version: str = "v1",
        http_method: str = "GET",
        auth_type: str = "api_key",
    ) -> Any:
        """Call a service method and parse its response.

        Args:
            interface: Service interface, e.g. "IFamilyGroupsService"
            method: Method name, e.g. "GetFamilyGroup"
            operation: What the call does, for error messages
                ("get family group")
            inputs: Method inputs, encoded by ``_service_inputs``
            model: Model for the response body; the raw body is returned
                when None
            version: Method version
            http_method: "GET" or "POST"
            auth_type: Credential to send ("api_key", "access_token", "none")

        Returns:
            The parsed model, or the raw JSON body

        Raises:
            ResponseParsingError: If the response does not fit ``model``
            SteamAPIError: On any other failure; see ``Client.request``
        """
        with self._errors(operation):
            data = await self._request(
                interface,
                method,
                version,
                params=self._service_inputs(inputs or {}),
                auth_type=auth_type,
                http_method=http_method,
            )
            return data if model is None else model.model_validate(data)

    @staticmethod
    def _indexed(name: str, values: Iterable[Any]) -> dict[str, str]:
        """Encode a repeated field the way the Web API expects it.

        Example:
            _indexed("appids_filter", [440, 620])
            -> {"appids_filter[0]": "440", "appids_filter[1]": "620"}
        """
        return {
            f"{name}[{index}]": _scalar(value) for index, value in enumerate(values)
        }

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
