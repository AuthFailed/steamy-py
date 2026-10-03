"""Main Steam Web API wrapper class."""

import logging
import os
import warnings

from aiohttp import ClientSession
from pydantic import ValidationError

from .client import Client
from .config import Settings
from .exceptions import ConfigurationError, ResponseParsingError
from .repos.economy import EconomyAPI
from .repos.family import FamilyAPI
from .repos.friends import FriendsAPI
from .repos.game import GameAPI
from .repos.library import LibraryAPI
from .repos.market import MarketAPI
from .repos.stats import StatsAPI
from .repos.store import StoreAPI
from .repos.users import UsersAPI
from .repos.util import UtilAPI
from .repos.wishlist import WishlistAPI
from .repos.workshop import WorkshopAPI

logger = logging.getLogger(__name__)


class Steam:
    """Main Steam Web API client.

    This is the primary entry point for interacting with the Steam Web API.
    Endpoints are grouped by namespace:

    - ``users``: profiles, friends lists, bans, vanity URLs, badges, levels
    - ``library``: owned and recently played games
    - ``stats``: achievements, stats, schemas, player counts
    - ``store``: app details, the app list, store search, news
    - ``wishlist``, ``workshop``, ``friends``, ``family``, ``util``
    - ``economy``: community inventories
    - ``market``: the community market

    Example:
        ```python
        import asyncio
        from steamy_py import Steam

        async def main():
            async with Steam(api_key="your_api_key") as steam:
                # Get player information
                player = await steam.users.get_player_summary("76561197960435530")
                print(f"Player: {player.personaname}")

                # Get owned games
                games = await steam.library.get_owned_games("76561197960435530")
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
        steam_login_secure: str | None = None,
        **kwargs,
    ):
        """Initialize the Steam API client.

        No credential is required: endpoints that need one raise
        ``AuthenticationError`` when it is missing.

        Args:
            api_key: Steam Web API key. Falls back to the STEAM_API_KEY
                environment variable.
            access_token: Steam access token for user-specific endpoints. Falls
                back to the STEAM_ACCESS_TOKEN environment variable.
            settings: Optional settings configuration
            session: Optional aiohttp session to reuse; it is never closed by
                this client
            steam_login_secure: ``steamLoginSecure`` cookie of a signed-in
                steamcommunity.com session, only for community endpoints that
                need a login (market price history). Falls back to the
                STEAM_LOGIN_SECURE environment variable.
            **kwargs: Settings fields (e.g. ``MAX_RETRIES=5``); applied on top
                of ``settings`` when both are given

        Raises:
            ConfigurationError: If a settings keyword is unknown or invalid

        Note:
            Each endpoint sends only the credential it needs:
            - Store, news, global stats, player counts, wishlists and util
              need none
            - ISteamUser and ISteamUserStats player methods need the API key
            - IPlayerService, IStoreService and IPublishedFileService methods
              take either
            - Family, friends list and last played times need the access
              token
        """
        api_key = api_key or os.getenv("STEAM_API_KEY")
        access_token = access_token or os.getenv("STEAM_ACCESS_TOKEN")
        steam_login_secure = steam_login_secure or os.getenv("STEAM_LOGIN_SECURE")

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
            steam_login_secure=steam_login_secure,
        )

        # API namespaces (#25)
        self.users = UsersAPI(self.client)
        self.library = LibraryAPI(self.client)
        self.stats = StatsAPI(self.client)
        self.store = StoreAPI(self.client)
        self.wishlist = WishlistAPI(self.client)
        self.workshop = WorkshopAPI(self.client)
        self.economy = EconomyAPI(self.client)
        self.market = MarketAPI(self.client)
        self.family = FamilyAPI(self.client)
        self.friends = FriendsAPI(self.client)
        self.util = UtilAPI(self.client)
        self._games = GameAPI(self.client)

        logger.debug("Steam API client initialized")

    @property
    def player(self) -> UsersAPI:
        """Deprecated: use ``users``."""
        warnings.warn(
            "Steam.player is deprecated; use Steam.users",
            DeprecationWarning,
            stacklevel=2,
        )
        return self.users

    @property
    def games(self) -> GameAPI:
        """Deprecated: use ``library``, ``store`` and ``stats``.

        Each method warns and calls its new home.
        """
        return self._games

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
            auth_type="any",
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
        """String representation; shows which credentials are set, masked."""
        credentials = {
            "api_key": self.client.api_key,
            "access_token": self.client.access_token,
            "steam_login_secure": self.client.steam_login_secure,
        }
        fields = [f"{name}='***'" for name, value in credentials.items() if value]
        fields.append(
            f"status='{'connected' if self.is_connected else 'disconnected'}'"
        )
        return f"Steam({', '.join(fields)})"
