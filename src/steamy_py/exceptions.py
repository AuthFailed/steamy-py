"""Custom exceptions for Steam API wrapper."""

from typing import Any


class SteamAPIError(Exception):
    """Base Steam API exception."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_data: dict[str, Any] | None = None,
    ):
        """Initialize Steam API error.

        Args:
            message: Error message
            status_code: HTTP status code if applicable
            response_data: API response data if applicable
        """
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data


class AuthenticationError(SteamAPIError):
    """Invalid or missing API key."""

    def __init__(self, message: str = "Invalid or missing Steam API key"):
        super().__init__(message, status_code=401)


class RateLimitError(SteamAPIError):
    """Rate limit exceeded."""

    def __init__(
        self, message: str = "Rate limit exceeded", retry_after: int | None = None
    ):
        super().__init__(message, status_code=429)
        self.retry_after = retry_after


class PlayerNotFoundError(SteamAPIError):
    """Player/Steam ID not found."""

    def __init__(self, steamid: str, message: str | None = None):
        if message is None:
            message = f"Player with Steam ID '{steamid}' not found"
        super().__init__(message, status_code=404)
        self.steamid = steamid


class GameNotFoundError(SteamAPIError):
    """Game/App ID not found."""

    def __init__(self, app_id: str, message: str | None = None):
        if message is None:
            message = f"Game with App ID '{app_id}' not found"
        super().__init__(message, status_code=404)
        self.app_id = app_id


class InvalidSteamIDError(SteamAPIError):
    """Invalid Steam ID format."""

    def __init__(self, steamid: str, message: str | None = None):
        if message is None:
            message = f"Invalid Steam ID format: '{steamid}'"
        super().__init__(message, status_code=400)
        self.steamid = steamid


class InvalidAppIDError(SteamAPIError):
    """Invalid App ID format."""

    def __init__(self, app_id: str, message: str | None = None):
        if message is None:
            message = f"Invalid App ID format: '{app_id}'"
        super().__init__(message, status_code=400)
        self.app_id = app_id


class PrivateProfileError(SteamAPIError):
    """Player profile is private or not accessible."""

    def __init__(self, steamid: str, message: str | None = None):
        if message is None:
            message = f"Profile for Steam ID '{steamid}' is private or not accessible"
        super().__init__(message, status_code=403)
        self.steamid = steamid


class ServiceUnavailableError(SteamAPIError):
    """Steam API service is temporarily unavailable."""

    def __init__(self, message: str = "Steam API service is temporarily unavailable"):
        super().__init__(message, status_code=503)


class ConfigurationError(SteamAPIError):
    """Configuration or setup error."""

    def __init__(self, message: str):
        super().__init__(message)


class ResponseParsingError(SteamAPIError):
    """Error parsing Steam API response."""

    def __init__(self, message: str, raw_response: str | None = None):
        super().__init__(message)
        self.raw_response = raw_response


class NetworkError(SteamAPIError):
    """Network or connection error."""

    def __init__(self, message: str, original_error: Exception | None = None):
        super().__init__(message)
        self.original_error = original_error
