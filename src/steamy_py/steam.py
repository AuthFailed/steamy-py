"""Main Steam Web API wrapper class."""

import logging

from .client import Client
from .config import Settings
from .exceptions import ConfigurationError
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
                price = await steam.market.get_item_price("AK-47 | Redline (Field-Tested)")
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
        **kwargs,
    ):
        """Initialize the Steam API client.

        Args:
            api_key: Steam API key for public endpoints. If not provided, will try to get from STEAM_API_KEY env var
            access_token: Steam access token for user-specific endpoints. If not provided, will try to get from STEAM_ACCESS_TOKEN env var
            settings: Optional settings configuration
            **kwargs: Additional arguments passed to Settings

        Raises:
            ConfigurationError: If no authentication credentials are provided

        Note:
            Some endpoints require api_key, others require access_token. You can provide one or both.
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
                "API key: Get from https://steamcommunity.com/dev/apikey (set STEAM_API_KEY env var) "
                "Access token: Get from Steam OAuth flow (set STEAM_ACCESS_TOKEN env var)"
            )

        # Initialize settings
        if settings is None:
            settings = Settings(**kwargs)

        # Initialize HTTP client
        self.client = Client(
            api_key=api_key, access_token=access_token, settings=settings
        )

        # Initialize API repositories
        self.player = PlayerAPI(self.client)
        self.games = GameAPI(self.client)
        self.market = MarketAPI(self.client)
        self.stats = StatsAPI(self.client)
        self.family = FamilyAPI(self.client)

        logger.info("Steam API client initialized")

    async def __aenter__(self):
        """Async context manager entry - creates session and authenticates."""
        await self.client.connect()
        logger.info("Steam API client connected")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes session."""
        await self.client.close()
        logger.info("Steam API client disconnected")

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

    async def test_connection(self) -> bool:
        """Test the Steam API connection and authentication.

        Returns:
            True if connection and authentication are working, False otherwise
        """
        try:
            if not self.is_connected:
                await self.connect()

            # Test with a simple API call
            await self.games.get_app_list()
            logger.info("Steam API connection test successful")
            return True

        except Exception as e:
            logger.error(f"Steam API connection test failed: {e}")
            return False

    async def get_api_key_info(self) -> dict:
        """Get information about the current API key usage.

        Note: Steam doesn't provide a direct endpoint for this, so this method
        attempts to make a test call and returns basic information.

        Returns:
            Dictionary with API key status information
        """
        try:
            if not self.is_connected:
                await self.connect()

            # Test API key with a simple call
            apps = await self.games.get_app_list()

            return {
                "valid": True,
                "connected": True,
                "test_result": f"Successfully retrieved {len(apps)} Steam applications",
            }

        except Exception as e:
            return {"valid": False, "connected": self.is_connected, "error": str(e)}

    def __repr__(self) -> str:
        """String representation of Steam client."""
        status = "connected" if self.is_connected else "disconnected"
        return f"Steam(api_key='***', status='{status}')"
