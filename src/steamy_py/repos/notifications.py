"""Notification endpoints (steam.notifications)."""

from ..models.notifications import SteamNotifications, SteamNotificationsResponse
from .base import BaseAPI


class NotificationsAPI(BaseAPI):
    """The signed-in user's Steam notifications (ISteamNotificationService)."""

    async def get_steam_notifications(
        self,
        *,
        include_hidden: bool = False,
        language: int | None = None,
        include_confirmation_count: bool = True,
        include_pinned_counts: bool = False,
        include_read: bool = True,
        count_only: bool = False,
    ) -> SteamNotifications:
        """Get the signed-in user's notifications and pending counts.

        Calls ISteamNotificationService/GetSteamNotifications with the access
        token; the user is the token's owner. The defaults are Steam's own,
        and every flag is always sent.

        Args:
            include_hidden: Include notifications the user has hidden
            language: Language of the notifications Steam localizes itself,
                as an ELanguage number; Steam's default (English) when None
            include_confirmation_count: Return ``confirmation_count``, the
                number of pending confirmations
            include_pinned_counts: Return ``pending_gift_count`` and
                ``pending_friend_count``
            include_read: Include notifications that were already read
            count_only: Return only the count of unread notifications
                (``unread_count``), not the notifications themselves

        Returns:
            The notifications (``body_data`` is JSON text; ``body`` parses
            it) and the counts; counts Steam leaves out are 0

        Raises:
            ValueError: If ``language`` is not an int
            AuthenticationError: If no access token is set
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        if language is not None and (
            isinstance(language, bool) or not isinstance(language, int)
        ):
            raise ValueError(f"language must be an ELanguage number: {language!r}")
        response = await self._call_service(
            "ISteamNotificationService",
            "GetSteamNotifications",
            "get Steam notifications",
            {
                "include_hidden": include_hidden,
                "language": language,
                "include_confirmation_count": include_confirmation_count,
                "include_pinned_counts": include_pinned_counts,
                "include_read": include_read,
                "count_only": count_only,
            },
            model=SteamNotificationsResponse,
            auth_type="access_token",
        )
        return response.response
