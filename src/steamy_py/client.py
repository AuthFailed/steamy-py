"""Async HTTP client with Steam API authentication and error handling."""

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import quote, quote_plus

import aiohttp
from aiohttp import ClientError, ClientSession, ClientTimeout

from ._version import __version__
from .config import Settings
from .exceptions import (
    NetworkError,
    RateLimitError,
    ResponseParsingError,
    SteamAPIError,
)

logger = logging.getLogger(__name__)

# Matches credential query parameters inside URLs embedded in error text.
_CREDENTIAL_PARAM_RE = re.compile(
    r"(?P<name>\b(?:key|access_token)=)[^&#\s'\"]+", re.IGNORECASE
)


class Client:
    """Async HTTP client with Steam API authentication."""

    def __init__(
        self,
        api_key: str | None = None,
        access_token: str | None = None,
        settings: Settings | None = None,
    ):
        """Initialize the client.

        Args:
            api_key: Steam API key for public endpoint authentication
            access_token: Steam access token for user-specific endpoint authentication
            settings: Optional settings configuration
        """
        self.api_key = api_key
        self.access_token = access_token
        self.settings = settings or Settings()
        self._session: ClientSession | None = None
        self._last_request_time = 0.0

        # Setup logging
        logging.basicConfig(
            level=getattr(logging, self.settings.LOG_LEVEL),
            format=self.settings.LOG_FORMAT,
        )

    async def __aenter__(self):
        """Async context manager entry - creates session."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes session."""
        await self.close()

    async def connect(self):
        """Initialize aiohttp session."""
        if self._session and not self._session.closed:
            return

        timeout = ClientTimeout(total=self.settings.REQUEST_TIMEOUT)
        connector = aiohttp.TCPConnector(limit=100)

        self._session = ClientSession(
            timeout=timeout,
            connector=connector,
            headers={
                "User-Agent": f"steamy-py/{__version__}",
                "Accept": "application/json",
            },
        )

        logger.info("Steam API client connected")

    async def close(self):
        """Close the session."""
        if self._session and not self._session.closed:
            await self._session.close()
            logger.info("Steam API client disconnected")

    async def _rate_limit(self):
        """Apply rate limiting if enabled."""
        if not self.settings.RATE_LIMIT_ENABLED:
            return

        now = time.time()
        time_since_last = now - self._last_request_time
        min_interval = 1.0 / self.settings.REQUESTS_PER_SECOND

        if time_since_last < min_interval:
            sleep_time = min_interval - time_since_last
            await asyncio.sleep(sleep_time)

        self._last_request_time = time.time()

    async def _get_session(self) -> ClientSession:
        """Return the open session, creating it if needed."""
        if self._session is None:
            await self.connect()
        assert self._session is not None
        return self._session

    def _apply_auth(self, params: dict[str, Any], auth_type: str) -> dict[str, Any]:
        """Return a copy of ``params`` with the credential for ``auth_type`` added."""
        params = dict(params)
        if auth_type == "api_key":
            if not self.api_key:
                raise ValueError("API key is required but not provided")
            params["key"] = self.api_key
        elif auth_type == "access_token":
            if not self.access_token:
                raise ValueError("Access token is required but not provided")
            params["access_token"] = self.access_token
        elif auth_type != "none":
            raise ValueError(
                f"Invalid auth_type: {auth_type}. "
                "Must be 'api_key', 'access_token', or 'none'"
            )
        return params

    async def _send(
        self,
        session: ClientSession,
        method: str,
        url: str,
        params: dict[str, Any],
        **kwargs,
    ) -> dict[str, Any]:
        """Send a single request and parse the JSON body.

        Raises:
            _RateLimitedError: On HTTP 429, after sleeping for ``Retry-After``
            ClientError: On HTTP errors
            ResponseParsingError: On invalid JSON response
        """
        async with session.request(method, url, params=params, **kwargs) as response:
            if response.status == 429:
                retry_after = float(
                    response.headers.get("Retry-After", self.settings.RETRY_DELAY)
                )
                logger.warning("Rate limited, sleeping for %s seconds", retry_after)
                await asyncio.sleep(retry_after)
                raise _RateLimitedError

            response.raise_for_status()

            try:
                data = await response.json()
            except (ValueError, aiohttp.ContentTypeError) as e:
                reason = self._describe_error(e)
            else:
                logger.debug("Successful response from %s", self._redact(url))
                return data

        # Raised outside the except block so the original aiohttp error (whose
        # text contains the full request URL) is not attached as __context__.
        message = f"Invalid JSON response from {self._redact(url)}: {reason}"
        logger.error("%s", message)
        raise ResponseParsingError(message)

    async def request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        auth_type: str = "api_key",
        **kwargs,
    ) -> dict[str, Any]:
        """Make authenticated request to Steam API.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Complete URL to request
            params: Query parameters
            auth_type: Authentication type ("api_key", "access_token", or "none")
            **kwargs: Additional aiohttp parameters

        Returns:
            JSON response data

        Raises:
            SteamAPIError: On HTTP errors (``status_code`` is set)
            RateLimitError: If every attempt was rate limited (HTTP 429)
            NetworkError: On connection errors
            ResponseParsingError: On invalid JSON response
            ValueError: If the credential for ``auth_type`` is missing

        Error messages and logs never contain the API key or access token.
        """
        session = await self._get_session()
        request_params = self._apply_auth(params or {}, auth_type)

        await self._rate_limit()

        # Only sanitized library exceptions leave this method. They are raised
        # after the loop, outside any except block, so the original aiohttp
        # error (which embeds the full URL with credentials) is never chained.
        failure: SteamAPIError | None = None
        for attempt in range(self.settings.MAX_RETRIES + 1):
            logger.debug(
                "Making %s request to %s (attempt %d)",
                method,
                self._redact(url),
                attempt + 1,
            )
            try:
                return await self._send(session, method, url, request_params, **kwargs)
            except _RateLimitedError:
                failure = RateLimitError(
                    "Rate limited by Steam (HTTP 429) on every attempt"
                )
                continue
            except ClientError as e:
                failure = self._to_library_error(e)

            if attempt < self.settings.MAX_RETRIES:
                sleep_time = self.settings.RETRY_DELAY * (2**attempt)
                logger.warning(
                    "Request failed (attempt %d), retrying in %s seconds: %s",
                    attempt + 1,
                    sleep_time,
                    failure,
                )
                await asyncio.sleep(sleep_time)
            else:
                logger.error(
                    "Request failed after %d attempts: %s",
                    self.settings.MAX_RETRIES + 1,
                    failure,
                )

        raise failure or SteamAPIError("Request failed for unknown reason")

    def _redact(self, text: str) -> str:
        """Remove the API key and access token from ``text``."""
        for secret in (self.api_key, self.access_token):
            if secret:
                for form in {secret, quote(secret, safe=""), quote_plus(secret)}:
                    text = text.replace(form, "***")
        return _CREDENTIAL_PARAM_RE.sub(r"\g<name>***", text)

    def _describe_error(self, error: BaseException) -> str:
        """Describe an aiohttp error without leaking credentials."""
        if isinstance(error, aiohttp.ClientResponseError):
            url = error.request_info.real_url.with_query(None)
            return self._redact(f"HTTP {error.status} {error.message} for {url}")
        return self._redact(f"{type(error).__name__}: {error}")

    def _to_library_error(self, error: ClientError) -> SteamAPIError:
        """Convert an aiohttp error into a sanitized library exception."""
        message = self._describe_error(error)
        if isinstance(error, aiohttp.ClientResponseError):
            return SteamAPIError(message, status_code=error.status)
        return NetworkError(message)


class _RateLimitedError(Exception):
    """Internal signal: the request hit HTTP 429 and should be retried."""
