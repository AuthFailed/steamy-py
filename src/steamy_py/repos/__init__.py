"""Repository modules for Steam API."""

from .auth import AuthAPI
from .base import BaseAPI
from .economy import EconomyAPI
from .family import FamilyAPI
from .friends import FriendsAPI
from .game import GameAPI
from .library import LibraryAPI
from .market import MarketAPI
from .notifications import NotificationsAPI
from .player import PlayerAPI
from .servers import ServersAPI
from .stats import StatsAPI
from .store import StoreAPI
from .users import UsersAPI
from .util import UtilAPI
from .wishlist import WishlistAPI
from .workshop import WorkshopAPI

__all__ = [
    "AuthAPI",
    "BaseAPI",
    "EconomyAPI",
    "FamilyAPI",
    "FriendsAPI",
    "GameAPI",
    "LibraryAPI",
    "MarketAPI",
    "NotificationsAPI",
    "PlayerAPI",
    "ServersAPI",
    "StatsAPI",
    "StoreAPI",
    "UsersAPI",
    "UtilAPI",
    "WishlistAPI",
    "WorkshopAPI",
]
