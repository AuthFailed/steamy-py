"""Main Steam Web API wrapper class."""

import logging

from aiohttp import ClientSession
from pydantic import ValidationError

from .client import Client
from .config import Settings
from .exceptions import ConfigurationError, ResponseParsingError
from .repos.family import FamilyAPI
from .repos.game import GameAPI
from .repos.market import MarketAPI
from .repos.player import PlayerAPI
from .repos.stats import StatsAPI

logger = logging.getLogger(__name__)


class Steam:
    """Main Steam Web API client.

    This is the primary entry point for interacting with the Steam Web API.
    It provides access to all API categories through dedicated repository objects.

    Example:
        ```python
        import asyncio
        from steamy_py import Steam

        async def main():
            async with Steam(api_key="your_api_key") as steam:
                # Get player information
                player = await steam.player.get_player_summary("76561197960435530")
                print(f"Player: {player.personaname}")

                # Get owned games
                games = await steam.games.get_owned_games("76561197960435530")
                print(f"Owns {len(games)} games")

                # Get market price
                price = await steam.market.get_item_price(
                    "AK-47 | Redline (Field-Tested)"
                )
                if price:
                    print(f"Price: {price.lowest_price}")

        asyncio.run(main())
        ```
    """

    def __init__(
        self,
        api_key: str | None = None,
        access_token: str | None = None,
        settings: Settings | None = None,
        session: ClientSession | None = None,
        **kwargs,
    ):
        """Initialize the Steam API client.

        Args:
            api_key: Steam API key for public endpoints. Falls back to the
                STEAM_API_KEY environment variable.
            access_token: Steam access token for user-specific endpoints. Falls
                back to the STEAM_ACCESS_TOKEN environment variable.
            settings: Optional settings configuration
            session: Optional aiohttp session to reuse; it is never closed by
                this client
            **kwargs: Settings fields (e.g. ``MAX_RETRIES=5``); applied on top
                of ``settings`` when both are given

        Raises:
            ConfigurationError: If no authentication credentials are provided,
                or a settings keyword is unknown or invalid

        Note:
            Some endpoints require api_key, others require access_token. You can
            provide one or both.
            - Player, Games, Stats APIs typically use api_key
            - Family, Friends, and other personal APIs typically use access_token
        """
        # Get credentials from parameters or environment
        if not api_key:
            import os

            api_key = os.getenv("STEAM_API_KEY")

        if not access_token:
            import os

            access_token = os.getenv("STEAM_ACCESS_TOKEN")

        if not api_key and not access_token:
            raise ConfigurationError(
                "Either Steam API key or access token is required. "
                "API key: Get from https://steamcommunity.com/dev/apikey "
                "(set STEAM_API_KEY env var). "
                "Access token: Get from Steam OAuth flow "
                "(set STEAM_ACCESS_TOKEN env var)"
            )

        # Initialize settings
        try:
            if settings is None:
                settings = Settings(**kwargs)
            elif kwargs:
                # Field names are case-insensitive; normalize so the override
                # replaces the dumped value instead of sitting next to it.
                overrides = {name.upper(): value for name, value in kwargs.items()}
                settings = Settings(**{**settings.model_dump(), **overrides})
        except ValidationError as e:
            raise ConfigurationError(f"Invalid settings: {e}") from e

        # Initialize HTTP client
        self.client = Client(
            api_key=api_key,
            access_token=access_token,
            settings=settings,
            session=session,
        )

        # Initialize API repositories
        self.player = PlayerAPI(self.client)
        self.games = GameAPI(self.client)
        self.market = MarketAPI(self.client)
        self.stats = StatsAPI(self.client)
        self.family = FamilyAPI(self.client)

        logger.debug("Steam API client initialized")

    async def __aenter__(self):
        """Async context manager entry - creates session and authenticates."""
        await self.client.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes session."""
        await self.client.close()

    async def connect(self):
        """Manually connect and authenticate.

        Note: This is called automatically when using the async context manager.
        """
        await self.client.connect()

    async def close(self):
        """Close the session.

        Note: This is called automatically when using the async context manager.
        """
        await self.client.close()

    @property
    def is_connected(self) -> bool:
        """Check if the client is connected."""
        return self.client._session is not None and not self.client._session.closed

    async def _check_connection(self) -> str:
        """Reach Steam, then make one cheap call with the configured credential.

        Returns:
            Which credential was checked ("api_key" or "access_token")

        Raises:
            SteamAPIError: If Steam is unreachable or rejects the credential
        """
        if not self.is_connected:
            await self.connect()

        base_url = self.client.settings.STEAM_API_BASE_URL.rstrip("/")
        server_info = await self.client.request(
            "GET", f"{base_url}/ISteamWebAPIUtil/GetServerInfo/v1/", auth_type="none"
        )
        if not isinstance(server_info, dict) or "servertime" not in server_info:
            raise ResponseParsingError("Unexpected GetServerInfo response from Steam")

        auth_type = "api_key" if self.client.api_key else "access_token"
        app_list = await self.client.request(
            "GET",
            f"{base_url}/IStoreService/GetAppList/v1/",
            params={"input_json": '{"max_results":1}'},
            auth_type=auth_type,
        )
        if not isinstance(app_list, dict) or "response" not in app_list:
            raise ResponseParsingError("Unexpected GetAppList response from Steam")
        return auth_type

    async def test_connection(self) -> bool:
        """Test the Steam API connection and authentication.

        Makes two small requests: ISteamWebAPIUtil/GetServerInfo, then one call
        with the API key (or the access token when there is no key).

        Returns:
            True if connection and authentication are working, False otherwise
        """
        try:
            await self._check_connection()
        except Exception as e:
            logger.warning("Steam API connection test failed: %s", e)
            return False
        logger.debug("Steam API connection test successful")
        return True

    async def get_api_key_info(self) -> dict:
        """Get information about the configured credential.

        Note: Steam doesn't provide a direct endpoint for this, so this method
        makes the same two small requests as ``test_connection``.

        Returns:
            Dictionary with credential status information
        """
        try:
            auth_type = await self._check_connection()
        except Exception as e:
            return {"valid": False, "connected": self.is_connected, "error": str(e)}

        credential = "API key" if auth_type == "api_key" else "Access token"
        return {
            "valid": True,
            "connected": True,
            "test_result": f"{credential} accepted by Steam",
        }

    def __repr__(self) -> str:
        """String representation of Steam client."""
        status = "connected" if self.is_connected else "disconnected"
        return f"Steam(api_key='***', status='{status}')"
