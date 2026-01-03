"""Async HTTP client with Steam API authentication and error handling."""

import asyncio
import logging
import time
from typing import Any

import aiohttp
from aiohttp import ClientError, ClientSession, ClientTimeout

from .config import Settings

logger = logging.getLogger(__name__)


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
                "User-Agent": "steam-py/1.0.0",
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
            ClientError: On HTTP errors
            ValueError: On invalid JSON response
        """
        if not self._session:
            await self.connect()

        # Add authentication to parameters
        if params is None:
            params = {}

        if auth_type == "api_key":
            if not self.api_key:
                raise ValueError("API key is required but not provided")
            params["key"] = self.api_key
        elif auth_type == "access_token":
            if not self.access_token:
                raise ValueError("Access token is required but not provided")
            params["access_token"] = self.access_token
        elif auth_type == "none":
            # No authentication required (for some public endpoints)
            pass
        else:
            raise ValueError(
                f"Invalid auth_type: {auth_type}. Must be 'api_key', 'access_token', or 'none'"
            )

        # Apply rate limiting
        await self._rate_limit()

        # Retry logic
        last_exception = None
        for attempt in range(self.settings.MAX_RETRIES + 1):
            try:
                logger.debug(
                    f"Making {method} request to {url} (attempt {attempt + 1})"
                )

                async with self._session.request(
                    method, url, params=params, **kwargs
                ) as response:
                    # Check for rate limiting
                    if response.status == 429:
                        retry_after = float(
                            response.headers.get(
                                "Retry-After", self.settings.RETRY_DELAY
                            )
                        )
                        logger.warning(
                            f"Rate limited, sleeping for {retry_after} seconds"
                        )
                        await asyncio.sleep(retry_after)
                        continue

                    # Raise for HTTP errors
                    response.raise_for_status()

                    # Parse JSON response
                    try:
                        data = await response.json()
                        logger.debug(f"Successful response from {url}")
                        return data
                    except (ValueError, aiohttp.ContentTypeError) as e:
                        logger.error(f"Invalid JSON response from {url}: {e}")
                        raise ValueError(f"Invalid JSON response: {e}")

            except ClientError as e:
                last_exception = e
                if attempt < self.settings.MAX_RETRIES:
                    sleep_time = self.settings.RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}), retrying in {sleep_time} seconds: {e}"
                    )
                    await asyncio.sleep(sleep_time)
                else:
                    logger.error(
                        f"Request failed after {self.settings.MAX_RETRIES + 1} attempts: {e}"
                    )

        raise last_exception or ClientError("Request failed for unknown reason")
