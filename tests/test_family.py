"""Tests for ``FamilyAPI``: IFamilyGroupsService (Steam Families).

Every call needs the user's access token. Each method is checked against
Steam's documented HTTP verb, RPC name and parameter names; the three calls
with typed results are also checked against realistic responses.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import pytest
from multidict import MultiDict

from steamy_py import (
    AuthenticationError,
    InvalidSteamIDError,
    RateLimitError,
    ResponseParsingError,
    Settings,
    Steam,
    SteamAPIError,
    SteamID,
)
from steamy_py.models.family import (
    FamilyGroupStatusResponse,
    PlaytimeSummaryResponse,
    SharedLibraryAppsResponse,
)
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

INTERFACE = "IFamilyGroupsService"

# Every IFamilyGroupsService method Steam documents (all are v1).
FAMILY_RPCS = (
    "CancelFamilyGroupInvite",
    "ClearCooldownSkip",
    "ConfirmInviteToFamilyGroup",
    "ConfirmJoinFamilyGroup",
    "CreateFamilyGroup",
    "DeleteFamilyGroup",
    "ForceAcceptInvite",
    "GetChangeLog",
    "GetFamilyGroup",
    "GetFamilyGroupForUser",
    "GetInviteCheckResults",
    "GetPlaytimeSummary",
    "GetPreferredLenders",
    "GetPurchaseRequests",
    "GetSharedLibraryApps",
    "GetUsersSharingDevice",
    "InviteToFamilyGroup",
    "JoinFamilyGroup",
    "ModifyFamilyGroupDetails",
    "RemoveFromFamilyGroup",
    "RequestPurchase",
    "ResendInvitationToFamilyGroup",
    "RespondToRequestedPurchase",
    "RollbackFamilyGroup",
    "SetFamilyCooldownOverrides",
    "SetPreferredLender",
    "UndeleteFamilyGroup",
)

FAMILY_GROUPID = 4223817
GROUP = str(FAMILY_GROUPID)
ADULT = "76561198012345678"
CHILD = "76561198087654321"
INVITEE = "76561198034567890"
INVITE_ID = 5512903876
NONCE = 7240931658820117
REQUEST_ID = 7300112
SHOPPING_CART = 1839205748113377
JOINED = 1727740800

EMPTY: dict[str, Any] = {"response": {}}
GROUP_FOR_USER: dict[str, Any] = load_fixture("family_group_for_user.json")
SHARED_LIBRARY: dict[str, Any] = load_fixture("family_shared_library_apps.json")
PLAYTIME: dict[str, Any] = load_fixture("family_playtime_summary.json")
FAMILY_GROUP: dict[str, Any] = {"response": GROUP_FOR_USER["response"]["family_group"]}

# What Steam answers to a signed-in user who has never joined a family.
NOT_A_MEMBER: dict[str, Any] = {
    "response": {"is_not_member_of_any_group": True, "cooldown_seconds_remaining": 0}
}

DEFAULT_LIBRARY_INPUTS = {
    "family_groupid": GROUP,
    "include_own": "0",
    "include_excluded": "0",
    "include_free": "0",
    "include_non_games": "0",
    "language": "english",
}

Call = Callable[[Steam], Awaitable[Any]]


@dataclass(frozen=True)
class Endpoint:
    """One ``FamilyAPI`` method, called with realistic arguments."""

    name: str
    call: Call
    rpc: str
    verb: str  # the HTTP verb Steam documents for ``rpc``
    inputs: dict[str, str]  # what Steam should receive, minus the credential
    reply: dict[str, Any] = field(default_factory=lambda: EMPTY)
    typed: bool = False  # True when the method returns a model, not the raw body


ENDPOINTS = [
    Endpoint(
        "cancel_family_group_invite",
        lambda steam: steam.family.cancel_family_group_invite(
            family_groupid=FAMILY_GROUPID, steamid_to_cancel=int(INVITEE)
        ),
        "CancelFamilyGroupInvite",
        "POST",
        {"family_groupid": GROUP, "steamid_to_cancel": INVITEE},
    ),
    Endpoint(
        "clear_cooldown_skip",
        lambda steam: steam.family.clear_cooldown_skip(
            steamid=int(INVITEE), invite_id=INVITE_ID
        ),
        "ClearCooldownSkip",
        "POST",
        {"steamid": INVITEE, "invite_id": str(INVITE_ID)},
    ),
    Endpoint(
        "confirm_invite_to_family_group",
        lambda steam: steam.family.confirm_invite_to_family_group(
            family_groupid=FAMILY_GROUPID, invite_id=INVITE_ID, nonce=NONCE
        ),
        "ConfirmInviteToFamilyGroup",
        "POST",
        {"family_groupid": GROUP, "invite_id": str(INVITE_ID), "nonce": str(NONCE)},
    ),
    Endpoint(
        "confirm_join_family_group",
        lambda steam: steam.family.confirm_join_family_group(
            family_groupid=FAMILY_GROUPID, invite_id=INVITE_ID, nonce=NONCE
        ),
        "ConfirmJoinFamilyGroup",
        "POST",
        {"family_groupid": GROUP, "invite_id": str(INVITE_ID), "nonce": str(NONCE)},
    ),
    Endpoint(
        "create_family_group",
        lambda steam: steam.family.create_family_group("The Walkers"),
        "CreateFamilyGroup",
        "POST",
        {"name": "The Walkers"},
        {"response": {"family_groupid": GROUP, "cooldown_skip_granted": True}},
    ),
    Endpoint(
        "delete_family_group",
        lambda steam: steam.family.delete_family_group(family_groupid=FAMILY_GROUPID),
        "DeleteFamilyGroup",
        "POST",
        {"family_groupid": GROUP},
    ),
    Endpoint(
        "force_accept_invite",
        lambda steam: steam.family.force_accept_invite(
            family_groupid=FAMILY_GROUPID, steamid=int(INVITEE)
        ),
        "ForceAcceptInvite",
        "POST",
        {"family_groupid": GROUP, "steamid": INVITEE},
    ),
    Endpoint(
        "get_change_log",
        lambda steam: steam.family.get_change_log(family_groupid=FAMILY_GROUPID),
        "GetChangeLog",
        "POST",
        {"family_groupid": GROUP},
        {
            "response": {
                "changes": [
                    {"timestamp": str(JOINED), "actor_steamid": STEAMID, "type": 1},
                    {
                        "timestamp": str(JOINED + 3600),
                        "actor_steamid": STEAMID,
                        "type": 4,
                    },
                ]
            }
        },
    ),
    Endpoint(
        "get_family_group",
        lambda steam: steam.family.get_family_group(
            FAMILY_GROUPID, send_running_apps=True
        ),
        "GetFamilyGroup",
        "GET",
        {"family_groupid": GROUP, "send_running_apps": "1"},
        FAMILY_GROUP,
    ),
    Endpoint(
        "get_family_group_for_user",
        lambda steam: steam.family.get_family_group_for_user(),
        "GetFamilyGroupForUser",
        "GET",
        {},
        GROUP_FOR_USER,
        typed=True,
    ),
    Endpoint(
        "get_invite_check_results",
        lambda steam: steam.family.get_invite_check_results(
            family_groupid=FAMILY_GROUPID, steamid=int(INVITEE)
        ),
        "GetInviteCheckResults",
        "GET",
        {"family_groupid": GROUP, "steamid": INVITEE},
        {"response": {"wallet_country_matches": True, "ip_match": True}},
    ),
    Endpoint(
        "get_playtime_summary",
        lambda steam: steam.family.get_playtime_summary(FAMILY_GROUPID),
        "GetPlaytimeSummary",
        "POST",
        {"family_groupid": GROUP},
        PLAYTIME,
        typed=True,
    ),
    Endpoint(
        "get_preferred_lenders",
        lambda steam: steam.family.get_preferred_lenders(family_groupid=FAMILY_GROUPID),
        "GetPreferredLenders",
        "GET",
        {"family_groupid": GROUP},
        {"response": {"members": [{"steamid": STEAMID, "preferred_appids": [620]}]}},
    ),
    Endpoint(
        "get_purchase_requests",
        lambda steam: steam.family.get_purchase_requests(
            [REQUEST_ID, REQUEST_ID + 1],
            family_groupid=FAMILY_GROUPID,
            include_completed=True,
            rt_include_completed_since=JOINED,
        ),
        "GetPurchaseRequests",
        "GET",
        {
            "request_ids[0]": str(REQUEST_ID),
            "request_ids[1]": str(REQUEST_ID + 1),
            "family_groupid": GROUP,
            "include_completed": "1",
            "rt_include_completed_since": str(JOINED),
        },
        {
            "response": {
                "requests": [
                    {
                        "requester_steamid": CHILD,
                        "gidshoppingcart": str(SHOPPING_CART),
                        "time_requested": JOINED + 86400,
                        "request_id": str(REQUEST_ID),
                        "requested_packageids": [7877],
                    }
                ]
            }
        },
    ),
    Endpoint(
        "get_shared_library_apps",
        lambda steam: steam.family.get_shared_library_apps(FAMILY_GROUPID),
        "GetSharedLibraryApps",
        "GET",
        DEFAULT_LIBRARY_INPUTS,
        SHARED_LIBRARY,
        typed=True,
    ),
    Endpoint(
        "get_users_sharing_device",
        lambda steam: steam.family.get_users_sharing_device(
            family_groupid=FAMILY_GROUPID,
            client_session_id=2,
            client_instance_id=8130470118852919,
        ),
        "GetUsersSharingDevice",
        "GET",
        {
            "family_groupid": GROUP,
            "client_session_id": "2",
            "client_instance_id": "8130470118852919",
        },
        {"response": {"users": [ADULT]}},
    ),
    Endpoint(
        "invite_to_family_group",
        lambda steam: steam.family.invite_to_family_group(
            family_groupid=FAMILY_GROUPID,
            receiver_steamid=int(INVITEE),
            receiver_role=2,
        ),
        "InviteToFamilyGroup",
        "POST",
        {"family_groupid": GROUP, "receiver_steamid": INVITEE, "receiver_role": "2"},
        {"response": {"invite_id": str(INVITE_ID), "two_factor_method": 1}},
    ),
    Endpoint(
        "join_family_group",
        lambda steam: steam.family.join_family_group(
            family_groupid=FAMILY_GROUPID, nonce=NONCE
        ),
        "JoinFamilyGroup",
        "POST",
        {"family_groupid": GROUP, "nonce": str(NONCE)},
        {"response": {"two_factor_method": 1}},
    ),
    Endpoint(
        "modify_family_group_details",
        lambda steam: steam.family.modify_family_group_details(
            family_groupid=FAMILY_GROUPID, name="Walker Family"
        ),
        "ModifyFamilyGroupDetails",
        "POST",
        {"family_groupid": GROUP, "name": "Walker Family"},
    ),
    Endpoint(
        "remove_from_family_group",
        lambda steam: steam.family.remove_from_family_group(
            family_groupid=FAMILY_GROUPID, steamid_to_remove=int(CHILD)
        ),
        "RemoveFromFamilyGroup",
        "POST",
        {"family_groupid": GROUP, "steamid_to_remove": CHILD},
    ),
    Endpoint(
        "request_purchase",
        lambda steam: steam.family.request_purchase(
            family_groupid=FAMILY_GROUPID,
            gid_shopping_cart=SHOPPING_CART,
            store_country_code="US",
        ),
        "RequestPurchase",
        "POST",
        {
            "family_groupid": GROUP,
            "gidshoppingcart": str(SHOPPING_CART),
            "store_country_code": "US",
        },
        {
            "response": {
                "gidshoppingcart": str(SHOPPING_CART),
                "request_id": str(REQUEST_ID),
            }
        },
    ),
    Endpoint(
        "resend_invitation_to_family_group",
        lambda steam: steam.family.resend_invitation_to_family_group(
            family_groupid=FAMILY_GROUPID, steamid=int(INVITEE)
        ),
        "ResendInvitationToFamilyGroup",
        "POST",
        {"family_groupid": GROUP, "steamid": INVITEE},
    ),
    Endpoint(
        "respond_to_requested_purchase",
        lambda steam: steam.family.respond_to_requested_purchase(
            family_groupid=FAMILY_GROUPID,
            purchase_requester_steamid=int(CHILD),
            action=2,
            request_id=REQUEST_ID,
        ),
        "RespondToRequestedPurchase",
        "POST",
        {
            "family_groupid": GROUP,
            "purchase_requester_steamid": CHILD,
            "action": "2",
            "request_id": str(REQUEST_ID),
        },
    ),
    Endpoint(
        "rollback_family_group",
        lambda steam: steam.family.rollback_family_group(
            family_groupid=FAMILY_GROUPID, rtime32_target=JOINED
        ),
        "RollbackFamilyGroup",
        "POST",
        {"family_groupid": GROUP, "rtime32_target": str(JOINED)},
    ),
    Endpoint(
        "set_family_cooldown_overrides",
        lambda steam: steam.family.set_family_cooldown_overrides(
            family_groupid=FAMILY_GROUPID, cooldown_count=1
        ),
        "SetFamilyCooldownOverrides",
        "POST",
        {"family_groupid": GROUP, "cooldown_count": "1"},
    ),
    Endpoint(
        "set_preferred_lender",
        lambda steam: steam.family.set_preferred_lender(
            family_groupid=FAMILY_GROUPID, appid=620, lender_steamid=int(ADULT)
        ),
        "SetPreferredLender",
        "POST",
        {"family_groupid": GROUP, "appid": "620", "lender_steamid": ADULT},
    ),
    Endpoint(
        "undelete_family_group",
        lambda steam: steam.family.undelete_family_group(family_groupid=FAMILY_GROUPID),
        "UndeleteFamilyGroup",
        "POST",
        {"family_groupid": GROUP},
    ),
]

ENDPOINTS_BY_NAME = {endpoint.name: endpoint for endpoint in ENDPOINTS}


def endpoint_params(
    marks: dict[str, pytest.MarkDecorator] | None = None,
    *,
    only_untyped: bool = False,
) -> list[Any]:
    """``ENDPOINTS`` as pytest params, with per-test ``marks`` by method name."""
    marks = marks or {}
    return [
        pytest.param(endpoint, id=endpoint.name, marks=marks.get(endpoint.name, ()))
        for endpoint in ENDPOINTS
        if not (only_untyped and endpoint.typed)
    ]


def rpc_path(rpc: str) -> str:
    return f"/{INTERFACE}/{rpc}/v1/"


def serve_every_rpc(fake_steam: FakeSteam, **reply: Any) -> None:
    """Answer every IFamilyGroupsService route, over GET and POST, with ``reply``.

    Used by the checks that must not depend on the RPC name or verb being right.
    """
    for rpc in FAMILY_RPCS:
        for verb in ("GET", "POST"):
            fake_steam.api(verb, rpc_path(rpc), **reply)


def sent_inputs(request: RecordedRequest) -> MultiDict[str]:
    """The inputs of ``request``: query string and form body together."""
    inputs: MultiDict[str] = MultiDict(request.query)
    inputs.extend(request.form)
    return inputs


def inputs_without_credential(request: RecordedRequest) -> list[tuple[str, str]]:
    """Sorted (name, value) inputs of ``request``, minus the access token."""
    return sorted(
        (name, value)
        for name, value in sent_inputs(request).items()
        if name != "access_token"
    )


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


# -- verbs, RPC names and parameters --------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    endpoint_params(),
)
async def test_call_uses_documented_verb_and_rpc(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    fake_steam.api(endpoint.verb, rpc_path(endpoint.rpc), json=endpoint.reply)

    await endpoint.call(steam)

    assert len(fake_steam.requests) == 1
    assert (fake_steam.last.method, fake_steam.last.path) == (
        endpoint.verb,
        rpc_path(endpoint.rpc),
    )


@pytest.mark.parametrize("endpoint", endpoint_params())
async def test_call_sends_inputs_under_documented_names(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    serve_every_rpc(fake_steam, json=endpoint.reply)

    await endpoint.call(steam)

    assert inputs_without_credential(fake_steam.last) == sorted(endpoint.inputs.items())


@pytest.mark.parametrize("endpoint", endpoint_params(only_untyped=True))
async def test_untyped_call_returns_response_body(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    serve_every_rpc(fake_steam, json=endpoint.reply)

    assert await endpoint.call(steam) == endpoint.reply


async def test_post_inputs_are_sent_in_form_body(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    endpoint = ENDPOINTS_BY_NAME["invite_to_family_group"]
    fake_steam.api("POST", rpc_path(endpoint.rpc), json=endpoint.reply)

    await endpoint.call(steam)

    sent = fake_steam.last
    assert {name: sent.form.get(name) for name in endpoint.inputs} == endpoint.inputs
    assert not set(endpoint.inputs) & set(sent.query)


# -- credentials -----------------------------------------------------------------


@pytest.mark.parametrize("endpoint", endpoint_params())
async def test_call_sends_access_token_not_api_key(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    serve_every_rpc(fake_steam, json=endpoint.reply)

    await endpoint.call(steam)

    assert len(fake_steam.requests) == 1
    inputs = sent_inputs(fake_steam.last)
    assert inputs.getall("access_token") == [ACCESS_TOKEN]
    assert "key" not in inputs
    assert "Authorization" not in fake_steam.last.headers


@pytest.mark.parametrize("endpoint", endpoint_params())
async def test_call_without_access_token_raises_before_any_request(
    key_only_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    serve_every_rpc(fake_steam, json=endpoint.reply)

    with pytest.raises(AuthenticationError, match="Access token is required"):
        await endpoint.call(key_only_steam)

    assert fake_steam.requests == []


async def test_client_with_only_an_access_token_can_call_family_api(
    token_only_steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetFamilyGroupForUser"), json=GROUP_FOR_USER)

    result = await token_only_steam.family.get_family_group_for_user()

    assert result.response.family_groupid == GROUP
    assert fake_steam.last.params == {"access_token": ACCESS_TOKEN}


# -- errors ----------------------------------------------------------------------


@pytest.mark.parametrize("endpoint", endpoint_params())
async def test_http_error_is_raised_as_steam_api_error(
    steam: Steam,
    fake_steam: FakeSteam,
    endpoint: Endpoint,
    caplog: pytest.LogCaptureFixture,
) -> None:
    serve_every_rpc(fake_steam, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(steam)

    assert len(fake_steam.requests) == 1
    assert "HTTP 500" in str(excinfo.value)
    assert ACCESS_TOKEN not in str(excinfo.value)
    assert ACCESS_TOKEN not in caplog.text


@pytest.mark.parametrize(
    "endpoint",
    [
        pytest.param(ENDPOINTS_BY_NAME[name], id=name)
        for name in (
            "get_family_group_for_user",
            "get_shared_library_apps",
            "get_playtime_summary",
        )
    ],
)
async def test_non_json_reply_is_raised_as_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    # Steam's edge servers answer some failures with an HTML page and 200.
    fake_steam.api(
        endpoint.verb,
        rpc_path(endpoint.rpc),
        text="<html><body>Service Unavailable</body></html>",
        content_type="text/html",
    )

    with pytest.raises(SteamAPIError, match="Invalid JSON response") as excinfo:
        await endpoint.call(steam)

    assert ACCESS_TOKEN not in str(excinfo.value)


@pytest.mark.parametrize(
    ("status", "error"),
    [
        pytest.param(500, SteamAPIError, id="http-500"),
        pytest.param(429, RateLimitError, id="http-429"),
    ],
)
async def test_http_error_keeps_status_code_and_exception_type(
    steam: Steam, fake_steam: FakeSteam, status: int, error: type[SteamAPIError]
) -> None:
    fake_steam.api(
        "GET",
        rpc_path("GetFamilyGroupForUser"),
        status=status,
        text="Error",
        headers={"Retry-After": "0"},
    )

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.family.get_family_group_for_user()

    assert type(excinfo.value) is error
    assert excinfo.value.status_code == status


@pytest.mark.parametrize(
    ("endpoint", "body"),
    [
        pytest.param(
            ENDPOINTS_BY_NAME["get_family_group_for_user"],
            {"response": {**GROUP_FOR_USER["response"], "membership_history": 1}},
            id="get_family_group_for_user",
        ),
        pytest.param(
            ENDPOINTS_BY_NAME["get_shared_library_apps"],
            {"response": {"apps": 1}},
            id="get_shared_library_apps",
        ),
        pytest.param(
            ENDPOINTS_BY_NAME["get_playtime_summary"],
            {"response": {"entries": 1}},
            id="get_playtime_summary",
        ),
    ],
)
async def test_malformed_response_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint, body: dict[str, Any]
) -> None:
    fake_steam.api(endpoint.verb, rpc_path(endpoint.rpc), json=body)

    with pytest.raises(ResponseParsingError):
        await endpoint.call(steam)


@pytest.mark.parametrize(
    ("endpoint", "other_operation"),
    [
        pytest.param(ENDPOINTS_BY_NAME[name], other, id=name)
        for name, other in [
            ("cancel_family_group_invite", "change log"),
            ("clear_cooldown_skip", "change log"),
            ("confirm_invite_to_family_group", "change log"),
            ("confirm_join_family_group", "change log"),
            ("create_family_group", "change log"),
            ("delete_family_group", "change log"),
            ("force_accept_invite", "change log"),
            ("invite_to_family_group", "join to family group"),
            ("join_family_group", "get invite to family group"),
            ("modify_family_group_details", "remove from family group"),
            ("set_preferred_lender", "get invite to family group"),
        ]
    ],
)
async def test_error_message_does_not_name_another_operation(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint, other_operation: str
) -> None:
    serve_every_rpc(fake_steam, status=500, text="Internal Server Error")

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(steam)

    assert other_operation not in str(excinfo.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        pytest.param(ENDPOINTS_BY_NAME[name], id=name)
        for name in ("get_family_group", "set_family_cooldown_overrides")
    ],
)
async def test_x_eresult_failure_raises_steam_api_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    # EResult 15 = AccessDenied; Steam still answers 200 with an empty response.
    fake_steam.api(
        endpoint.verb,
        rpc_path(endpoint.rpc),
        json=EMPTY,
        headers={"x-eresult": "15"},
    )

    with pytest.raises(SteamAPIError):
        await endpoint.call(steam)


# -- GetFamilyGroupForUser ---------------------------------------------------------


async def test_get_family_group_for_user_sends_no_steamid_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetFamilyGroupForUser"), json=GROUP_FOR_USER)

    await steam.family.get_family_group_for_user()

    assert fake_steam.last.params == {"access_token": ACCESS_TOKEN}


async def test_get_family_group_for_user_sends_given_steamid(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetFamilyGroupForUser"), json=GROUP_FOR_USER)

    await steam.family.get_family_group_for_user(steamid=int(STEAMID))

    assert fake_steam.last.params == {"steamid": STEAMID, "access_token": ACCESS_TOKEN}


async def test_get_family_group_for_user_can_include_family_group(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetFamilyGroupForUser"), json=GROUP_FOR_USER)

    await steam.family.get_family_group_for_user(include_family_group_response=True)

    assert fake_steam.last.params == {
        "include_family_group_response": "1",
        "access_token": ACCESS_TOKEN,
    }


async def test_get_family_group_for_user_parses_member_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetFamilyGroupForUser"), json=GROUP_FOR_USER)

    result = await steam.family.get_family_group_for_user()

    assert isinstance(result, FamilyGroupStatusResponse)
    status = result.response
    assert status.family_groupid == GROUP
    assert status.is_not_member_of_any_group is False
    assert status.latest_time_joined == JOINED
    assert status.latest_joined_family_groupid == GROUP
    assert status.role == 1
    assert status.cooldown_seconds_remaining == 0
    assert status.can_undelete_last_joined_family is False
    assert [
        (entry.family_groupid, entry.rtime_joined, entry.rtime_left, entry.role)
        for entry in status.membership_history
    ] == [("3988120", 1695326573, 1696118400, 2), (GROUP, JOINED, 0, 1)]
    assert [entry.participated for entry in status.membership_history] == [
        False,
        True,
    ]


async def test_get_family_group_for_user_parses_non_member_response(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetFamilyGroupForUser"), json=NOT_A_MEMBER)

    result = await steam.family.get_family_group_for_user()

    status = result.response
    assert status.is_not_member_of_any_group is True
    assert status.cooldown_seconds_remaining == 0
    assert status.membership_history == []


async def test_get_family_group_for_user_parses_response_with_defaults_omitted(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # A member: false/zero/empty fields are left out of the JSON.
    body = {
        "response": {
            "family_groupid": GROUP,
            "latest_time_joined": JOINED,
            "latest_joined_family_groupid": GROUP,
            "role": 1,
        }
    }
    fake_steam.api("GET", rpc_path("GetFamilyGroupForUser"), json=body)

    result = await steam.family.get_family_group_for_user()

    status = result.response
    assert status.family_groupid == GROUP
    assert status.is_not_member_of_any_group is False
    assert status.cooldown_seconds_remaining == 0
    assert status.can_undelete_last_joined_family is False
    assert status.membership_history == []


async def test_get_family_group_for_user_keeps_pending_invites_and_family_group(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetFamilyGroupForUser"), json=GROUP_FOR_USER)

    result = await steam.family.get_family_group_for_user()

    status = result.response
    assert [
        (invite.family_groupid, invite.inviter_steamid, invite.invite_id)
        for invite in status.pending_group_invites
    ] == [("5017342", "76561198045678901", str(INVITE_ID))]
    assert status.family_group.name == "The Walkers"
    assert [member.steamid for member in status.family_group.members] == [
        STEAMID,
        ADULT,
        CHILD,
    ]


# -- GetSharedLibraryApps ------------------------------------------------------------


async def test_get_shared_library_apps_sends_defaults(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetSharedLibraryApps"), json=SHARED_LIBRARY)

    await steam.family.get_shared_library_apps(FAMILY_GROUPID)

    assert fake_steam.last.params == {
        **DEFAULT_LIBRARY_INPUTS,
        "access_token": ACCESS_TOKEN,
    }


async def test_get_shared_library_apps_sends_every_option(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetSharedLibraryApps"), json=SHARED_LIBRARY)

    await steam.family.get_shared_library_apps(
        FAMILY_GROUPID,
        include_own=True,
        include_excluded=True,
        include_free=True,
        include_non_games=True,
        language="german",
        max_apps=100,
        steamid=int(STEAMID),
    )

    assert fake_steam.last.params == {
        "family_groupid": GROUP,
        "include_own": "1",
        "include_excluded": "1",
        "include_free": "1",
        "include_non_games": "1",
        "language": "german",
        "max_apps": "100",
        "steamid": STEAMID,
        "access_token": ACCESS_TOKEN,
    }


async def test_get_shared_library_apps_omits_options_passed_as_none(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetSharedLibraryApps"), json=SHARED_LIBRARY)

    await steam.family.get_shared_library_apps(
        FAMILY_GROUPID,
        include_own=None,  # type: ignore[arg-type]
        language=None,  # type: ignore[arg-type]
    )

    sent = fake_steam.last.params
    assert "include_own" not in sent
    assert "language" not in sent
    assert sent["family_groupid"] == GROUP
    assert sent["access_token"] == ACCESS_TOKEN


async def test_get_shared_library_apps_parses_apps(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetSharedLibraryApps"), json=SHARED_LIBRARY)

    result = await steam.family.get_shared_library_apps(FAMILY_GROUPID)

    assert isinstance(result, SharedLibraryAppsResponse)
    half_life, portal, tf2 = result.response.apps
    assert half_life.appid == 220
    assert half_life.name == "Half-Life 2"
    assert half_life.owner_steamids == [ADULT]
    assert half_life.capsule_filename == "capsule_184x69.jpg"
    assert half_life.img_icon_hash == "fcfb366051782b8ebf2aa297f3b746395858cb62"
    assert half_life.exclude_reason == 0
    assert half_life.rt_time_acquired == 1101772800
    assert half_life.rt_last_played == 1729036800
    assert half_life.rt_playtime == 2835
    assert half_life.app_type == 1
    assert half_life.content_descriptors == [2, 5]
    assert portal.owner_steamids == [STEAMID, ADULT]
    assert portal.content_descriptors == []
    assert tf2.exclude_reason == 3


async def test_get_shared_library_apps_parses_empty_library(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetSharedLibraryApps"), json=EMPTY)

    result = await steam.family.get_shared_library_apps(FAMILY_GROUPID)

    assert result.response.apps == []


async def test_get_shared_library_apps_parses_app_with_defaults_omitted(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    # Steamworks Common Redistributables: no name, art or playtime in the reply.
    body = {
        "response": {
            "apps": [
                {
                    "appid": 228980,
                    "owner_steamids": [ADULT],
                    "exclude_reason": 2,
                    "rt_time_acquired": 1303171200,
                    "app_type": 4,
                }
            ],
            "owner_steamid": STEAMID,
        }
    }
    fake_steam.api("GET", rpc_path("GetSharedLibraryApps"), json=body)

    result = await steam.family.get_shared_library_apps(FAMILY_GROUPID)

    (app,) = result.response.apps
    assert (app.appid, app.exclude_reason, app.app_type) == (228980, 2, 4)
    assert (app.name, app.rt_last_played, app.rt_playtime) == ("", 0, 0)
    assert app.content_descriptors == []


async def test_get_shared_library_apps_keeps_owner_steamid_and_sort_as(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetSharedLibraryApps"), json=SHARED_LIBRARY)

    result = await steam.family.get_shared_library_apps(FAMILY_GROUPID)

    assert result.response.owner_steamid == STEAMID
    assert result.response.apps[0].sort_as == "Half-Life 2"


# -- GetPlaytimeSummary ---------------------------------------------------------------


async def test_get_playtime_summary_parses_entries(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", rpc_path("GetPlaytimeSummary"), json=PLAYTIME)

    result = await steam.family.get_playtime_summary(FAMILY_GROUPID)

    assert isinstance(result, PlaytimeSummaryResponse)
    assert [
        (
            entry.steamid,
            entry.appid,
            entry.first_played,
            entry.latest_played,
            entry.seconds_played,
        )
        for entry in result.response.entries
    ] == [
        (ADULT, 620, 1727913600, 1730246400, 80520),
        (CHILD, 220, 1728086400, 1729036800, 170100),
    ]


async def test_get_playtime_summary_parses_empty_summary(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", rpc_path("GetPlaytimeSummary"), json=EMPTY)

    result = await steam.family.get_playtime_summary(FAMILY_GROUPID)

    assert result.response.entries == []


async def test_get_playtime_summary_keeps_entries_by_owner(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", rpc_path("GetPlaytimeSummary"), json=PLAYTIME)

    result = await steam.family.get_playtime_summary(FAMILY_GROUPID)

    assert [
        (entry.steamid, entry.appid, entry.seconds_played)
        for entry in result.response.entries_by_owner
    ] == [(STEAMID, 620, 80520)]


# -- GetPurchaseRequests and RequestPurchase ------------------------------------------


async def test_get_purchase_requests_sends_family_and_completion_filters(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    endpoint = ENDPOINTS_BY_NAME["get_purchase_requests"]
    fake_steam.api("GET", rpc_path(endpoint.rpc), json=endpoint.reply)

    assert await endpoint.call(steam) == endpoint.reply

    params = fake_steam.last.params
    assert params["family_groupid"] == GROUP
    assert params["include_completed"] == "1"
    assert params["rt_include_completed_since"] == str(JOINED)


async def test_get_purchase_requests_sends_no_request_ids_by_default(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", rpc_path("GetPurchaseRequests"), json=EMPTY)

    await steam.family.get_purchase_requests(family_groupid=FAMILY_GROUPID)

    assert not any(name.startswith("request_ids") for name in fake_steam.last.params)


# -- input encoding ------------------------------------------------------------------


async def test_zero_inputs_are_sent_not_dropped(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", rpc_path("JoinFamilyGroup"), json=EMPTY)

    await steam.family.join_family_group(family_groupid=0, nonce=0)

    assert inputs_without_credential(fake_steam.last) == [
        ("family_groupid", "0"),
        ("nonce", "0"),
    ]


async def test_64_bit_ids_are_accepted_as_strings(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", rpc_path("ConfirmJoinFamilyGroup"), json=EMPTY)

    await steam.family.confirm_join_family_group(
        family_groupid=GROUP, invite_id=str(INVITE_ID), nonce=str(NONCE)
    )

    assert inputs_without_credential(fake_steam.last) == sorted(
        {
            "family_groupid": GROUP,
            "invite_id": str(INVITE_ID),
            "nonce": str(NONCE),
        }.items()
    )


@pytest.mark.parametrize("steamid", [INVITEE, int(INVITEE), SteamID(INVITEE)])
async def test_steamid_inputs_accept_int_str_and_steamid(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    fake_steam.api("POST", rpc_path("InviteToFamilyGroup"), json=EMPTY)

    await steam.family.invite_to_family_group(
        family_groupid=FAMILY_GROUPID, receiver_steamid=steamid, receiver_role=1
    )

    assert sent_inputs(fake_steam.last)["receiver_steamid"] == INVITEE


@pytest.mark.parametrize("bad_id", ["robinwalker", "103582791429521412", True])
async def test_invalid_steamid_input_is_rejected_before_any_request(
    steam: Steam, fake_steam: FakeSteam, bad_id: Any
) -> None:
    serve_every_rpc(fake_steam, json=EMPTY)

    with pytest.raises(InvalidSteamIDError):
        await steam.family.remove_from_family_group(
            family_groupid=FAMILY_GROUPID, steamid_to_remove=bad_id
        )

    assert fake_steam.requests == []
