"""Tests for ``steam.notifications``: ISteamNotificationService/GetSteamNotifications.

The method is about the signed-in user and needs the access token; it never
sends the API key. notifications_steam_notifications.json is built from
service_steamnotification.proto; its wishlist notification has the body
published in gofurry/steam-go's tests. No recorded replies were found.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from steamy_py import (
    AuthenticationError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
)
from steamy_py.models.notifications import (
    ESteamNotificationType,
    SteamNotificationData,
    SteamNotifications,
)
from tests.fakesteam import ACCESS_TOKEN, API_KEY, FakeSteam, load_fixture

PATH = "/ISteamNotificationService/GetSteamNotifications/v1/"
NOTIFICATIONS: dict[str, Any] = load_fixture("notifications_steam_notifications.json")

# Every flag, sent with Steam's own defaults.
DEFAULT_FLAGS = {
    "include_hidden": "0",
    "include_confirmation_count": "1",
    "include_pinned_counts": "0",
    "include_read": "1",
    "count_only": "0",
}


@pytest.fixture
async def key_only_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client that has a Web API key but no access token."""
    async with Steam(api_key=API_KEY, settings=settings) as client:
        yield client


@pytest.fixture
async def token_only_steam(settings: Settings) -> AsyncIterator[Steam]:
    """A client that has an access token but no Web API key."""
    async with Steam(access_token=ACCESS_TOKEN, settings=settings) as client:
        yield client


# -- request ---------------------------------------------------------------------


async def test_is_one_get_to_v1_with_default_flags_and_access_token_only(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=NOTIFICATIONS)

    await steam.notifications.get_steam_notifications()

    assert [(r.method, r.path) for r in fake_steam.requests] == [("GET", PATH)]
    # The client has an API key too, but only the token is sent.
    assert fake_steam.last.params == {**DEFAULT_FLAGS, "access_token": ACCESS_TOKEN}
    assert "Authorization" not in fake_steam.last.headers


async def test_sends_every_flag_and_language(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=NOTIFICATIONS)

    await steam.notifications.get_steam_notifications(
        include_hidden=True,
        language=6,
        include_confirmation_count=False,
        include_pinned_counts=True,
        include_read=False,
        count_only=True,
    )

    assert fake_steam.last.params == {
        "include_hidden": "1",
        "language": "6",
        "include_confirmation_count": "0",
        "include_pinned_counts": "1",
        "include_read": "0",
        "count_only": "1",
        "access_token": ACCESS_TOKEN,
    }


async def test_works_with_access_token_only(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=NOTIFICATIONS)

    result = await token_only_steam.notifications.get_steam_notifications()

    assert result.unread_count == 2
    assert fake_steam.last.params == {**DEFAULT_FLAGS, "access_token": ACCESS_TOKEN}


async def test_without_access_token_raises_before_request(
    key_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=NOTIFICATIONS)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await key_only_steam.notifications.get_steam_notifications()

    assert fake_steam.requests == []


@pytest.mark.parametrize("language", ["english", True, 6.0], ids=repr)
async def test_rejects_language_that_is_not_an_int_before_request(
    steam: Steam, fake_steam: FakeSteam, language: Any
) -> None:
    fake_steam.api("GET", PATH, json=NOTIFICATIONS)

    with pytest.raises(ValueError, match="ELanguage"):
        await steam.notifications.get_steam_notifications(language=language)

    assert fake_steam.requests == []


async def test_flags_are_keyword_only(steam: Steam) -> None:
    with pytest.raises(TypeError):
        await steam.notifications.get_steam_notifications(True)  # type: ignore[misc]


# -- response --------------------------------------------------------------------


async def test_parses_notifications_and_counts(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json=NOTIFICATIONS)

    result = await steam.notifications.get_steam_notifications()

    assert isinstance(result, SteamNotifications)
    assert (
        result.confirmation_count,
        result.pending_gift_count,
        result.pending_friend_count,
        result.unread_count,
        result.pending_family_invite_count,
    ) == (1, 0, 1, 2, 0)
    wishlist, trade, invite = result.notifications
    assert all(isinstance(n, SteamNotificationData) for n in (wishlist, trade, invite))
    assert wishlist.model_dump() == NOTIFICATIONS["response"]["notifications"][0]
    assert wishlist.notification_type == ESteamNotificationType.WISHLIST
    assert wishlist.body == {"appid": 1139900, "count": 1}

    assert (trade.notification_id, trade.notification_type) == ("147789012345", 9)
    assert ESteamNotificationType(trade.notification_type).name == "TRADE_OFFER"
    assert (trade.read, trade.hidden, trade.viewed) == (True, False, 1727223000)
    assert trade.body == {"sender": "76561198012345678", "tradeofferid": "7456123987"}

    # Fields Steam leaves out keep their defaults.
    assert invite.notification_type == ESteamNotificationType.FRIEND_INVITE
    assert (invite.read, invite.hidden, invite.expiry, invite.viewed) == (
        False,
        False,
        0,
        0,
    )


async def test_empty_response_gives_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json={"response": {}})

    result = await steam.notifications.get_steam_notifications()

    assert result == SteamNotifications()
    assert result.notifications == []
    assert result.unread_count == 0


async def test_count_only_reply_has_counts_without_notifications(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, json={"response": {"unread_count": 19}})

    result = await steam.notifications.get_steam_notifications(count_only=True)

    assert (result.notifications, result.unread_count) == ([], 19)


async def test_unknown_notification_type_is_kept_as_int(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET",
        PATH,
        json={"response": {"notifications": [{"notification_type": 99}]}},
    )

    [notification] = (await steam.notifications.get_steam_notifications()).notifications

    assert notification.notification_type == 99


@pytest.mark.parametrize("body_data", ["", "not json", "{"], ids=repr)
def test_body_is_none_without_json(body_data: str) -> None:
    assert SteamNotificationData(body_data=body_data).body is None


def test_notification_type_values_match_the_proto() -> None:
    assert len(ESteamNotificationType) == 31
    assert [member.value for member in ESteamNotificationType] == list(range(31))
    assert ESteamNotificationType.TWO_FACTOR_PROMPT == 25
    assert ESteamNotificationType.REPORTED_CONTENT_ACTION == 30


# -- errors ----------------------------------------------------------------------


async def test_http_error_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", PATH, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.notifications.get_steam_notifications()

    assert excinfo.value.status_code == 500
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert len(fake_steam.requests) == 1


@pytest.mark.parametrize(
    "body",
    [
        pytest.param(
            {"response": {"notifications": [{"timestamp": "today"}]}},
            id="non-numeric-timestamp",
        ),
        pytest.param(
            {"response": {"notifications": {"notification_id": "1"}}},
            id="notifications-not-a-list",
        ),
        pytest.param({"response": {"unread_count": "many"}}, id="non-numeric-count"),
        pytest.param({"response": []}, id="response-not-an-object"),
    ],
)
async def test_malformed_body_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, body: dict[str, Any]
) -> None:
    fake_steam.api("GET", PATH, json=body)

    with pytest.raises(ResponseParsingError, match="Failed to get Steam notifications"):
        await steam.notifications.get_steam_notifications()
