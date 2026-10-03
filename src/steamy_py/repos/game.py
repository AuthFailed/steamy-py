"""Deprecated: ``GameAPI`` (``steam.games``) was split up in 2.0.

Owned games moved to ``Steam.library``, the app list, app details and game
search to ``Steam.store``, and achievements and schemas to ``Steam.stats``.
Every method here still works, warns, and calls its new home.
"""

from collections.abc import AsyncIterator
from typing import Any

from ..models.game import (
    Achievement,
    AppDetails,
    AppListResponse,
    GameSchema,
    OwnedGame,
    SteamApp,
)
from ..steamid import SteamIDLike
from .base import BaseAPI
from .library import LibraryAPI
from .stats import StatsAPI
from .store import StoreAPI


class GameAPI(BaseAPI):
    """Deprecated: use ``Steam.library``, ``Steam.store`` and ``Steam.stats``."""

    async def get_owned_games(
        self, steamid: SteamIDLike, *args: Any, **kwargs: Any
    ) -> list[OwnedGame]:
        """Deprecated: use ``Steam.library.get_owned_games``."""
        self._deprecated("GameAPI.get_owned_games", "Steam.library.get_owned_games")
        return await LibraryAPI(self.client).get_owned_games(steamid, *args, **kwargs)

    async def get_app_list_page(self, *args: Any, **kwargs: Any) -> AppListResponse:
        """Deprecated: use ``Steam.store.get_app_list_page``."""
        self._deprecated("GameAPI.get_app_list_page", "Steam.store.get_app_list_page")
        return await StoreAPI(self.client).get_app_list_page(*args, **kwargs)

    async def iter_app_list(self, *args: Any, **kwargs: Any) -> AsyncIterator[SteamApp]:
        """Deprecated: use ``Steam.store.iter_app_list``."""
        self._deprecated("GameAPI.iter_app_list", "Steam.store.iter_app_list")
        async for app in StoreAPI(self.client).iter_app_list(*args, **kwargs):
            yield app

    async def get_app_list(self, *args: Any, **kwargs: Any) -> list[SteamApp]:
        """Deprecated: use ``Steam.store.get_app_list``."""
        self._deprecated("GameAPI.get_app_list", "Steam.store.get_app_list")
        return await StoreAPI(self.client).get_app_list(*args, **kwargs)

    async def get_player_achievements(
        self, steamid: SteamIDLike, app_id: int, language: str = "english"
    ) -> list[Achievement]:
        """Deprecated: use ``Steam.stats.get_player_achievements``."""
        self._deprecated(
            "GameAPI.get_player_achievements", "Steam.stats.get_player_achievements"
        )
        return await StatsAPI(self.client).get_player_achievements(
            steamid, app_id, language
        )

    async def get_schema_for_game(
        self, app_id: int, language: str = "english"
    ) -> GameSchema:
        """Deprecated: use ``Steam.stats.get_schema_for_game``."""
        self._deprecated(
            "GameAPI.get_schema_for_game", "Steam.stats.get_schema_for_game"
        )
        return await StatsAPI(self.client).get_schema_for_game(app_id, language)

    async def get_app_details(
        self, app_id: int, country: str = "US", language: str = "english"
    ) -> AppDetails | None:
        """Deprecated: use ``Steam.store.get_app_details``."""
        self._deprecated("GameAPI.get_app_details", "Steam.store.get_app_details")
        return await StoreAPI(self.client).get_app_details(app_id, country, language)

    async def search_games(
        self, search_term: str, owned_games: list[OwnedGame] | None = None
    ) -> list[SteamApp]:
        """Deprecated: use ``Steam.store.search_games``."""
        self._deprecated("GameAPI.search_games", "Steam.store.search_games")
        return await StoreAPI(self.client).search_games(search_term, owned_games)
