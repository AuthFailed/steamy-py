"""Models for ISteamNotificationService responses.

Service methods leave out every field Steam has no value for, so every field
has a default. Notification ids (uint64) arrive as strings and are kept as
strings. ``notification_type`` is kept as ``int`` so new types still parse;
``ESteamNotificationType`` names the known values.
"""

import json
from enum import IntEnum
from typing import Any

from pydantic import Field

from .base import SteamModel


class ESteamNotificationType(IntEnum):
    """Kind of notification (``SteamNotificationData.notification_type``).

    Values from ``ESteamNotificationType`` in Steam's
    steammessages_notifications.steamclient.proto.
    """

    INVALID = 0
    TEST = 1
    GIFT = 2
    COMMENT = 3
    ITEM = 4
    FRIEND_INVITE = 5
    MAJOR_SALE = 6
    PRELOAD_AVAILABLE = 7
    WISHLIST = 8
    TRADE_OFFER = 9
    GENERAL = 10
    HELP_REQUEST = 11
    ASYNC_GAME = 12
    CHAT_MSG = 13
    MODERATOR_MSG = 14
    PARENTAL_FEATURE_ACCESS_REQUEST = 15
    FAMILY_INVITE = 16
    FAMILY_PURCHASE_REQUEST = 17
    PARENTAL_PLAYTIME_REQUEST = 18
    FAMILY_PURCHASE_REQUEST_RESPONSE = 19
    PARENTAL_FEATURE_ACCESS_RESPONSE = 20
    PARENTAL_PLAYTIME_RESPONSE = 21
    REQUESTED_GAME_ADDED = 22
    SEND_TO_PHONE = 23
    CLIP_DOWNLOADED = 24
    TWO_FACTOR_PROMPT = 25  # k_ESteamNotificationType_2FAPrompt
    MOBILE_CONFIRMATION = 26
    PARTNER_EVENT = 27
    PLAYTEST_INVITE = 28
    TRADE_REVERSAL = 29
    REPORTED_CONTENT_ACTION = 30


class SteamNotificationData(SteamModel):
    """One notification (``SteamNotificationData``)."""

    notification_id: str = Field(default="", description="Notification id (64-bit)")
    notification_targets: int = Field(
        default=0, description="Bit field of where the notification is shown"
    )
    notification_type: int = Field(
        default=0, description="Kind of notification (ESteamNotificationType)"
    )
    body_data: str = Field(
        default="", description="Type-specific details, as JSON text"
    )
    read: bool = Field(default=False, description="Whether it has been read")
    timestamp: int = Field(default=0, description="When it was sent (Unix timestamp)")
    hidden: bool = Field(default=False, description="Whether the user hid it")
    expiry: int = Field(
        default=0,
        description="When it expires (Unix timestamp, unverified); 0 when not sent",
    )
    viewed: int = Field(
        default=0,
        description="When it was viewed (Unix timestamp, unverified); 0 when not sent",
    )

    @property
    def body(self) -> Any:
        """``body_data`` parsed from JSON, or None if it is empty or not JSON."""
        if not self.body_data:
            return None
        try:
            return json.loads(self.body_data)
        except ValueError:
            return None


class SteamNotifications(SteamModel):
    """The signed-in user's notifications and pending counts.

    Body of ``CSteamNotification_GetSteamNotifications_Response``.
    """

    notifications: list[SteamNotificationData] = Field(default_factory=list)
    confirmation_count: int = Field(
        default=0, description="Pending confirmations, when requested"
    )
    pending_gift_count: int = Field(
        default=0, description="Unclaimed gifts, when pinned counts are requested"
    )
    pending_friend_count: int = Field(
        default=0,
        description="Pending friend requests, when pinned counts are requested",
    )
    unread_count: int = Field(default=0, description="Unread notifications")
    pending_family_invite_count: int = Field(
        default=0, description="Pending Steam Family invites"
    )


class SteamNotificationsResponse(SteamModel):
    """Response wrapper for ISteamNotificationService/GetSteamNotifications."""

    response: SteamNotifications = Field(default_factory=SteamNotifications)
