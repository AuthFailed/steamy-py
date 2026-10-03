"""Notification endpoints (steam.notifications)."""

from .base import BaseAPI


class NotificationsAPI(BaseAPI):
    """The signed-in user's Steam notifications (ISteamNotificationService)."""
