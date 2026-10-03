"""Tests for ``AuthAPI`` (steam.auth): IAuthenticationService sign-in helpers.

- ``begin_auth_session_via_qr``: BeginAuthSessionViaQR, POST, nested inputs as
  one ``input_json`` form field
- ``poll_auth_session_status``: PollAuthSessionStatus, POST form
- ``generate_access_token_for_app``: GenerateAccessTokenForApp, POST form; the
  refresh token is the credential
- ``wait_for_qr_approval``: polls PollAuthSessionStatus on a virtual clock

None of them may send the client's API key or access token. The refresh
token, and every token Steam returns, must stay out of URLs, logs, exception
messages and ``repr()``.

The fixtures are built from the CAuthentication_* messages in
SteamDatabase/Protobufs (steam/steammessages_auth.steamclient.proto) in their
JSON form (uint64 as a string, bytes as base64), with the shapes reported for
live replies: challenge_url https://s.team/q/1/<client_id>, a 16-byte
request_id and a 5 second interval. The tokens are test values.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

import steamy_py.repos.auth as auth_module
from steamy_py import (
    AuthenticationError,
    InvalidSteamIDError,
    ResponseParsingError,
    Steam,
    SteamAPIError,
)
from steamy_py.models.auth import (
    AppAccessToken,
    AuthSessionStatus,
    EAuthSessionGuardType,
    EAuthTokenPlatformType,
    ETokenRenewalType,
    QRAuthSession,
)
from tests.conftest import make_settings
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    STEAMID,
    FakeSteam,
    RecordedRequest,
    load_fixture,
)

BEGIN_PATH = "/IAuthenticationService/BeginAuthSessionViaQR/v1/"
POLL_PATH = "/IAuthenticationService/PollAuthSessionStatus/v1/"
GENERATE_PATH = "/IAuthenticationService/GenerateAccessTokenForApp/v1/"

QR_SESSION: dict[str, Any] = load_fixture("auth_begin_auth_session_via_qr.json")
APPROVED: dict[str, Any] = load_fixture("auth_poll_auth_session_status.json")
APP_TOKEN: dict[str, Any] = load_fixture("auth_generate_access_token_for_app.json")
PENDING: dict[str, Any] = {"response": {}}

CLIENT_ID = QR_SESSION["response"]["client_id"]
# Has "+", "/" and "=", which must reach Steam unchanged.
REQUEST_ID = QR_SESSION["response"]["request_id"]
REFRESH_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJFZERTQSJ9.input-refresh-token+/="
POLL_REFRESH = APPROVED["response"]["refresh_token"]
POLL_ACCESS = APPROVED["response"]["access_token"]
APP_ACCESS = APP_TOKEN["response"]["access_token"]
RENEWED_REFRESH = "eyJ0eXAiOiJKV1QiLCJhbGciOiJFZERTQSJ9.renewed-refresh-token"
GUARD_DATA = "eyJ0eXAiOiJKV1QiLCJhbGciOiJFZERTQSJ9.guard-data"

# Every secret that must never be logged or put in an error message.
SECRETS = [
    REFRESH_TOKEN,
    POLL_REFRESH,
    POLL_ACCESS,
    APP_ACCESS,
    RENEWED_REFRESH,
    GUARD_DATA,
    API_KEY,
    ACCESS_TOKEN,
]


@dataclass(frozen=True)
class Endpoint:
    """One ``AuthAPI`` request method, called with realistic arguments."""

    name: str
    call: Callable[[Steam], Awaitable[Any]]
    path: str
    reply: dict[str, Any]
    malformed: Any  # JSON that does not fit the method's model
    operation: str  # what the error message says failed

    def serve(self, fake_steam: FakeSteam, **reply: Any) -> None:
        """Register ``reply`` (default: the realistic one) for this method."""
        fake_steam.api("POST", self.path, **(reply or {"json": self.reply}))


ENDPOINTS = [
    Endpoint(
        "begin_auth_session_via_qr",
        lambda steam: steam.auth.begin_auth_session_via_qr(),
        BEGIN_PATH,
        QR_SESSION,
        {"response": {"interval": "soon"}},
        "begin QR auth session",
    ),
    Endpoint(
        "poll_auth_session_status",
        lambda steam: steam.auth.poll_auth_session_status(CLIENT_ID, REQUEST_ID),
        POLL_PATH,
        APPROVED,
        {"response": {"had_remote_interaction": "maybe"}},
        "poll auth session status",
    ),
    Endpoint(
        "generate_access_token_for_app",
        lambda steam: steam.auth.generate_access_token_for_app(REFRESH_TOKEN, STEAMID),
        GENERATE_PATH,
        APP_TOKEN,
        {"response": {"access_token": ["not", "a", "string"]}},
        "generate access token",
    ),
]


def endpoint_params(endpoints: list[Endpoint]) -> Any:
    return pytest.mark.parametrize(
        "endpoint", [pytest.param(endpoint, id=endpoint.name) for endpoint in endpoints]
    )


def form_of(request: RecordedRequest) -> dict[str, str]:
    """The form body of ``request``, checking that no name was sent twice and
    nothing went in the query string."""
    items = list(request.form.items())
    assert len({name for name, _ in items}) == len(items), items
    assert dict(request.query) == {}
    return dict(items)


def assert_no_credential(request: RecordedRequest) -> None:
    """Check that ``request`` carries none of the client's credentials."""
    for pairs in (request.query, request.form):
        assert "key" not in pairs
        assert "access_token" not in pairs
    assert API_KEY.encode() not in request.body
    assert ACCESS_TOKEN.encode() not in request.body
    assert "Cookie" not in request.headers
    assert "Authorization" not in request.headers


def assert_no_secret_in(*texts: str, secrets: list[str] = SECRETS) -> None:
    """Check that no secret, nor its last 16 characters, is in ``texts``.

    The tail matters: pydantic shortens long inputs in error messages by
    cutting out their middle, which still shows the end of a token.
    """
    for text in texts:
        for secret in secrets:
            assert secret not in text
            assert secret[-16:] not in text


@pytest.fixture
async def anonymous_steam(settings: Any) -> AsyncIterator[Steam]:
    """A client with no credential at all."""
    async with Steam(settings=settings) as client:
        yield client


@pytest.fixture
async def retrying_steam(fake_steam: FakeSteam) -> AsyncIterator[Steam]:
    """A client with credentials that retries failed requests."""
    async with Steam(
        api_key=API_KEY,
        access_token=ACCESS_TOKEN,
        settings=make_settings(fake_steam, MAX_RETRIES=2),
    ) as client:
        yield client


# -- every method -------------------------------------------------------------


@endpoint_params(ENDPOINTS)
async def test_call_is_one_post_to_v1_without_any_credential(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(steam)

    assert [(r.method, r.path) for r in fake_steam.requests] == [
        ("POST", endpoint.path)
    ]
    assert_no_credential(fake_steam.last)


@endpoint_params(ENDPOINTS)
async def test_works_with_a_client_without_credentials(
    anonymous_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam)

    await endpoint.call(anonymous_steam)

    assert len(fake_steam.requests) == 1


@endpoint_params(ENDPOINTS)
async def test_http_500_is_raised_once_as_steam_api_error(
    retrying_steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, text="Transport error 2", status=500)

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(retrying_steam)

    assert type(excinfo.value) is SteamAPIError
    assert excinfo.value.status_code == 500
    # A sign-in POST that may have reached Steam is never repeated.
    assert len(fake_steam.requests) == 1


@endpoint_params(ENDPOINTS)
async def test_malformed_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, json=endpoint.malformed)

    with pytest.raises(ResponseParsingError, match=f"Failed to {endpoint.operation}"):
        await endpoint.call(steam)


@endpoint_params(ENDPOINTS)
async def test_non_json_reply_raises_response_parsing_error(
    steam: Steam, fake_steam: FakeSteam, endpoint: Endpoint
) -> None:
    endpoint.serve(fake_steam, text="<html>Error</html>", content_type="text/html")

    with pytest.raises(ResponseParsingError, match="Invalid JSON response"):
        await endpoint.call(steam)


# -- begin_auth_session_via_qr ------------------------------------------------


async def test_begin_sends_device_details_as_input_json_in_form(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", BEGIN_PATH, json=QR_SESSION)

    await steam.auth.begin_auth_session_via_qr()

    form = form_of(fake_steam.last)
    assert list(form) == ["input_json"]
    assert json.loads(form["input_json"]) == {
        "device_friendly_name": "steamy-py",
        "platform_type": 2,
        "device_details": {"device_friendly_name": "steamy-py", "platform_type": 2},
    }


async def test_begin_sends_every_option(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("POST", BEGIN_PATH, json=QR_SESSION)

    await steam.auth.begin_auth_session_via_qr(
        device_friendly_name="Kitchen tablet",
        platform_type=EAuthTokenPlatformType.MOBILE_APP,
        os_type=-500,
        gaming_device_type=528,
        website_id="Mobile",
    )

    assert json.loads(form_of(fake_steam.last)["input_json"]) == {
        "device_friendly_name": "Kitchen tablet",
        "platform_type": 3,
        "device_details": {
            "device_friendly_name": "Kitchen tablet",
            "platform_type": 3,
            "os_type": -500,
            "gaming_device_type": 528,
        },
        "website_id": "Mobile",
    }


async def test_begin_parses_session(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("POST", BEGIN_PATH, json=QR_SESSION)

    session = await steam.auth.begin_auth_session_via_qr()

    assert isinstance(session, QRAuthSession)
    assert session.client_id == "6097734395127281917"
    assert session.challenge_url == "https://s.team/q/1/6097734395127281917"
    assert session.request_id == REQUEST_ID
    assert session.interval == 5.0
    (confirmation,) = session.allowed_confirmations
    assert confirmation.confirmation_type == EAuthSessionGuardType.DEVICE_CONFIRMATION
    assert confirmation.associated_message == ""
    assert session.version == 1
    # request_id lets anyone collect the tokens, so repr() leaves it out.
    assert REQUEST_ID not in repr(session)
    assert REQUEST_ID not in str(session)


async def test_begin_parses_empty_response(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("POST", BEGIN_PATH, json=PENDING)

    session = await steam.auth.begin_auth_session_via_qr()

    assert session == QRAuthSession()
    assert (session.client_id, session.request_id, session.interval) == ("", "", 0.0)
    assert session.allowed_confirmations == []


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        pytest.param({"device_friendly_name": ""}, "device_friendly_name", id="name"),
        pytest.param({"device_friendly_name": None}, "device_friendly_name", id="none"),
        pytest.param({"platform_type": 9}, "platform_type", id="unknown-platform"),
        pytest.param({"platform_type": True}, "platform_type", id="bool-platform"),
        pytest.param({"platform_type": "2"}, "platform_type", id="str-platform"),
        pytest.param({"os_type": 2**31}, "os_type", id="os-type-range"),
        pytest.param({"os_type": True}, "os_type", id="os-type-bool"),
        pytest.param({"gaming_device_type": -1}, "gaming_device_type", id="gdt"),
        pytest.param({"website_id": " "}, "website_id", id="website-id"),
    ],
)
async def test_begin_rejects_invalid_inputs_before_any_request(
    steam: Steam, fake_steam: FakeSteam, kwargs: dict[str, Any], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        await steam.auth.begin_auth_session_via_qr(**kwargs)

    assert fake_steam.requests == []


# -- poll_auth_session_status -------------------------------------------------


async def test_poll_sends_client_and_request_id_in_form(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", POLL_PATH, json=PENDING)

    await steam.auth.poll_auth_session_status(CLIENT_ID, REQUEST_ID)

    assert form_of(fake_steam.last) == {
        "client_id": CLIENT_ID,
        "request_id": REQUEST_ID,
    }
    assert REQUEST_ID.encode() not in fake_steam.last.path.encode()


async def test_poll_sends_token_to_revoke(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("POST", POLL_PATH, json=PENDING)

    await steam.auth.poll_auth_session_status(
        int(CLIENT_ID), REQUEST_ID, token_to_revoke="18446744073709551615"
    )

    assert form_of(fake_steam.last) == {
        "client_id": CLIENT_ID,
        "request_id": REQUEST_ID,
        "token_to_revoke": "18446744073709551615",
    }


async def test_poll_parses_approved_status(steam: Steam, fake_steam: FakeSteam) -> None:
    fake_steam.api("POST", POLL_PATH, json=APPROVED)

    status = await steam.auth.poll_auth_session_status(CLIENT_ID, REQUEST_ID)

    assert isinstance(status, AuthSessionStatus)
    assert status.is_approved
    assert status.refresh_token == POLL_REFRESH
    assert status.access_token == POLL_ACCESS
    assert status.had_remote_interaction is True
    assert status.account_name == "steamy_test_account"
    assert (status.new_client_id, status.new_challenge_url) == ("", "")
    assert status.new_guard_data == status.agreement_session_url == ""


async def test_poll_parses_pending_status(steam: Steam, fake_steam: FakeSteam) -> None:
    # Not yet scanned: Steam leaves every field out.
    fake_steam.api("POST", POLL_PATH, json=PENDING)

    status = await steam.auth.poll_auth_session_status(CLIENT_ID, REQUEST_ID)

    assert status == AuthSessionStatus()
    assert not status.is_approved
    assert status.had_remote_interaction is False


async def test_poll_parses_rotated_challenge(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "POST",
        POLL_PATH,
        json={
            "response": {
                "new_client_id": "6097734395127281918",
                "new_challenge_url": "https://s.team/q/1/6097734395127281918",
                "had_remote_interaction": True,
            }
        },
    )

    status = await steam.auth.poll_auth_session_status(CLIENT_ID, REQUEST_ID)

    assert status.new_client_id == "6097734395127281918"
    assert status.new_challenge_url == "https://s.team/q/1/6097734395127281918"
    assert status.had_remote_interaction is True
    assert not status.is_approved


@pytest.mark.parametrize(
    "client_id", [0, -1, True, "", "abc", " 1", 2**64, "18446744073709551616", 1.5]
)
async def test_poll_rejects_invalid_client_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, client_id: Any
) -> None:
    with pytest.raises(ValueError, match="Invalid client id"):
        await steam.auth.poll_auth_session_status(client_id, REQUEST_ID)

    assert fake_steam.requests == []


@pytest.mark.parametrize("request_id", ["", "  ", None, b"\x01\x02"])
async def test_poll_rejects_empty_request_id_before_any_request(
    steam: Steam, fake_steam: FakeSteam, request_id: Any
) -> None:
    with pytest.raises(ValueError, match="request_id must be a non-empty string"):
        await steam.auth.poll_auth_session_status(CLIENT_ID, request_id)

    assert fake_steam.requests == []


@pytest.mark.parametrize("token_id", [0, True, "token"])
async def test_poll_rejects_invalid_token_to_revoke_before_any_request(
    steam: Steam, fake_steam: FakeSteam, token_id: Any
) -> None:
    with pytest.raises(ValueError, match="Invalid token id"):
        await steam.auth.poll_auth_session_status(
            CLIENT_ID, REQUEST_ID, token_to_revoke=token_id
        )

    assert fake_steam.requests == []


# -- generate_access_token_for_app --------------------------------------------


async def test_generate_posts_refresh_token_and_steamid_in_form(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", GENERATE_PATH, json=APP_TOKEN)

    await steam.auth.generate_access_token_for_app(REFRESH_TOKEN, int(STEAMID))

    request = fake_steam.last
    assert form_of(request) == {"refresh_token": REFRESH_TOKEN, "steamid": STEAMID}
    assert REFRESH_TOKEN not in request.path
    assert_no_credential(request)


@pytest.mark.parametrize(
    ("renewal_type", "sent"),
    [(ETokenRenewalType.ALLOW, "1"), (ETokenRenewalType.NONE, "0"), (1, "1")],
)
async def test_generate_sends_renewal_type(
    steam: Steam, fake_steam: FakeSteam, renewal_type: int, sent: str
) -> None:
    fake_steam.api("POST", GENERATE_PATH, json=APP_TOKEN)

    await steam.auth.generate_access_token_for_app(
        REFRESH_TOKEN, STEAMID, renewal_type=renewal_type
    )

    assert form_of(fake_steam.last)["renewal_type"] == sent


async def test_generate_parses_access_token(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", GENERATE_PATH, json=APP_TOKEN)

    tokens = await steam.auth.generate_access_token_for_app(REFRESH_TOKEN, STEAMID)

    assert isinstance(tokens, AppAccessToken)
    assert tokens.access_token == APP_ACCESS
    assert tokens.refresh_token == ""


async def test_generate_parses_renewed_refresh_token(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "POST",
        GENERATE_PATH,
        json={
            "response": {"access_token": APP_ACCESS, "refresh_token": RENEWED_REFRESH}
        },
    )

    tokens = await steam.auth.generate_access_token_for_app(
        REFRESH_TOKEN, STEAMID, ETokenRenewalType.ALLOW
    )

    assert (tokens.access_token, tokens.refresh_token) == (APP_ACCESS, RENEWED_REFRESH)
    assert tokens.model_dump() == {
        "access_token": APP_ACCESS,
        "refresh_token": RENEWED_REFRESH,
    }


async def test_generate_empty_response_raises_authentication_error(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("POST", GENERATE_PATH, json=PENDING)

    with pytest.raises(AuthenticationError, match="no access token") as excinfo:
        await steam.auth.generate_access_token_for_app(REFRESH_TOKEN, STEAMID)

    assert excinfo.value.status_code is None
    assert_no_secret_in(str(excinfo.value), repr(excinfo.value))


async def test_generate_refused_refresh_token_raises_authentication_error(
    steam: Steam, fake_steam: FakeSteam, caplog: pytest.LogCaptureFixture
) -> None:
    # What Steam answers for a refresh token it will not renew: HTTP 200, an
    # empty body and EResult 15 (AccessDenied).
    caplog.set_level(logging.DEBUG)
    fake_steam.api(
        "POST", GENERATE_PATH, text="", status=200, headers={"x-eresult": "15"}
    )

    with pytest.raises(AuthenticationError) as excinfo:
        await steam.auth.generate_access_token_for_app(REFRESH_TOKEN, STEAMID)

    assert excinfo.value.eresult == 15
    assert len(fake_steam.requests) == 1
    assert_no_secret_in(str(excinfo.value), repr(excinfo.value), caplog.text)


@pytest.mark.parametrize("refresh_token", ["", "   ", None, b"token"])
async def test_generate_rejects_empty_refresh_token_before_any_request(
    steam: Steam, fake_steam: FakeSteam, refresh_token: Any
) -> None:
    with pytest.raises(ValueError, match="refresh_token must be a non-empty string"):
        await steam.auth.generate_access_token_for_app(refresh_token, STEAMID)

    assert fake_steam.requests == []


@pytest.mark.parametrize("steamid", ["", "robinwalker", True, "103582791429521412"])
async def test_generate_rejects_invalid_steamid_before_any_request(
    steam: Steam, fake_steam: FakeSteam, steamid: Any
) -> None:
    with pytest.raises(InvalidSteamIDError) as excinfo:
        await steam.auth.generate_access_token_for_app(REFRESH_TOKEN, steamid)

    assert fake_steam.requests == []
    assert REFRESH_TOKEN not in str(excinfo.value)


@pytest.mark.parametrize("renewal_type", [2, -1, True, "1"])
async def test_generate_rejects_invalid_renewal_type_before_any_request(
    steam: Steam, fake_steam: FakeSteam, renewal_type: Any
) -> None:
    with pytest.raises(ValueError, match="Invalid renewal_type") as excinfo:
        await steam.auth.generate_access_token_for_app(
            REFRESH_TOKEN, STEAMID, renewal_type=renewal_type
        )

    assert fake_steam.requests == []
    assert REFRESH_TOKEN not in str(excinfo.value)


# -- secrets stay secret --------------------------------------------------------


async def test_tokens_are_left_out_of_repr_and_str_but_not_model_dump() -> None:
    status = AuthSessionStatus(
        refresh_token=POLL_REFRESH,
        access_token=POLL_ACCESS,
        new_guard_data=GUARD_DATA,
        account_name="steamy_test_account",
    )
    tokens = AppAccessToken(access_token=APP_ACCESS, refresh_token=RENEWED_REFRESH)

    assert_no_secret_in(repr(status), str(status), repr(tokens), str(tokens))
    assert "steamy_test_account" in repr(status)
    assert status.model_dump()["refresh_token"] == POLL_REFRESH
    assert status.model_dump()["new_guard_data"] == GUARD_DATA
    assert tokens.model_dump()["access_token"] == APP_ACCESS


async def test_no_secret_is_logged_or_raised_on_success(
    steam: Steam, fake_steam: FakeSteam, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    fake_steam.api("POST", POLL_PATH, json=APPROVED)
    fake_steam.api(
        "POST",
        GENERATE_PATH,
        json={
            "response": {"access_token": APP_ACCESS, "refresh_token": RENEWED_REFRESH}
        },
    )

    status = await steam.auth.poll_auth_session_status(CLIENT_ID, REQUEST_ID)
    tokens = await steam.auth.generate_access_token_for_app(
        REFRESH_TOKEN, STEAMID, ETokenRenewalType.ALLOW
    )

    assert caplog.records, "expected the request to be logged"
    assert_no_secret_in(caplog.text, repr(status), repr(tokens))
    assert_no_secret_in(caplog.text, secrets=[REQUEST_ID])
    # The refresh token went in the form body, not the URL.
    assert all(REFRESH_TOKEN not in str(r.query) for r in fake_steam.requests)


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param({"text": "Internal Server Error", "status": 500}, id="http-500"),
        pytest.param({"json": {"error": "denied"}, "status": 401}, id="http-401"),
        pytest.param({"json": {}, "headers": {"x-eresult": "15"}}, id="eresult-15"),
        pytest.param({"text": "<html>oops</html>"}, id="not-json"),
    ],
)
async def test_refresh_token_is_not_logged_or_raised_on_errors(
    steam: Steam,
    fake_steam: FakeSteam,
    caplog: pytest.LogCaptureFixture,
    reply: dict[str, Any],
) -> None:
    caplog.set_level(logging.DEBUG)
    fake_steam.api("POST", GENERATE_PATH, **reply)

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.auth.generate_access_token_for_app(REFRESH_TOKEN, STEAMID)

    assert_no_secret_in(str(excinfo.value), repr(excinfo.value), caplog.text)
    assert_no_secret_in(str(excinfo.value.response_data))


@pytest.mark.parametrize(
    ("path", "body", "call"),
    [
        pytest.param(
            POLL_PATH,
            {
                "response": {
                    "refresh_token": POLL_REFRESH,
                    "access_token": POLL_ACCESS,
                    "new_guard_data": GUARD_DATA,
                    "had_remote_interaction": "not-a-bool",
                }
            },
            lambda steam: steam.auth.poll_auth_session_status(CLIENT_ID, REQUEST_ID),
            id="poll-bad-field-next-to-tokens",
        ),
        pytest.param(
            POLL_PATH,
            {"response": {"refresh_token": {"value": POLL_REFRESH}}},
            lambda steam: steam.auth.poll_auth_session_status(CLIENT_ID, REQUEST_ID),
            id="poll-token-of-wrong-type",
        ),
        pytest.param(
            GENERATE_PATH,
            {"response": {"access_token": APP_ACCESS, "refresh_token": [1]}},
            lambda steam: steam.auth.generate_access_token_for_app(
                REFRESH_TOKEN, STEAMID
            ),
            id="generate-bad-refresh-token",
        ),
        pytest.param(
            GENERATE_PATH,
            {"response": [APP_ACCESS, RENEWED_REFRESH]},
            lambda steam: steam.auth.generate_access_token_for_app(
                REFRESH_TOKEN, STEAMID
            ),
            id="generate-response-not-an-object",
        ),
        pytest.param(
            BEGIN_PATH,
            {"response": {"request_id": [REQUEST_ID, POLL_REFRESH]}},
            lambda steam: steam.auth.begin_auth_session_via_qr(),
            id="begin-bad-request-id",
        ),
    ],
)
async def test_malformed_reply_does_not_leak_tokens(
    steam: Steam,
    fake_steam: FakeSteam,
    caplog: pytest.LogCaptureFixture,
    path: str,
    body: Any,
    call: Callable[[Steam], Awaitable[Any]],
) -> None:
    caplog.set_level(logging.DEBUG)
    fake_steam.api("POST", path, json=body)

    with pytest.raises(ResponseParsingError) as excinfo:
        await call(steam)

    texts = (str(excinfo.value), repr(excinfo.value), caplog.text)
    assert_no_secret_in(*texts)
    assert_no_secret_in(*texts, secrets=[REQUEST_ID])


# -- wait_for_qr_approval (virtual time) ----------------------------------------


class VirtualClock:
    """Stands in for the monotonic clock and ``asyncio.sleep``."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, delay: float) -> None:
        self.sleeps.append(delay)
        self.now += delay


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> VirtualClock:
    virtual = VirtualClock()
    monkeypatch.setattr(auth_module, "_monotonic", virtual.monotonic)
    monkeypatch.setattr(auth_module, "_sleep", virtual.sleep)
    return virtual


def qr_session(**overrides: Any) -> QRAuthSession:
    return QRAuthSession.model_validate({**QR_SESSION["response"], **overrides})


async def test_wait_polls_at_the_interval_until_approved(
    steam: Steam, fake_steam: FakeSteam, clock: VirtualClock
) -> None:
    fake_steam.api("POST", POLL_PATH, json=PENDING)
    fake_steam.api(
        "POST", POLL_PATH, json={"response": {"had_remote_interaction": True}}
    )
    fake_steam.api("POST", POLL_PATH, json=APPROVED)

    status = await steam.auth.wait_for_qr_approval(qr_session(), timeout=60)

    assert status.is_approved
    assert status.access_token == POLL_ACCESS
    assert clock.sleeps == [5.0, 5.0]
    assert [form_of(r) for r in fake_steam.requests] == [
        {"client_id": CLIENT_ID, "request_id": REQUEST_ID}
    ] * 3


async def test_wait_returns_without_sleeping_when_already_approved(
    steam: Steam, fake_steam: FakeSteam, clock: VirtualClock
) -> None:
    fake_steam.api("POST", POLL_PATH, json=APPROVED)

    status = await steam.auth.wait_for_qr_approval(qr_session())

    assert status.refresh_token == POLL_REFRESH
    assert clock.sleeps == []
    assert len(fake_steam.requests) == 1


async def test_wait_switches_to_new_client_id(
    steam: Steam, fake_steam: FakeSteam, clock: VirtualClock
) -> None:
    fake_steam.api(
        "POST",
        POLL_PATH,
        json={"response": {"new_client_id": "6097734395127281918"}},
    )
    fake_steam.api("POST", POLL_PATH, json=PENDING)
    fake_steam.api("POST", POLL_PATH, json=APPROVED)

    await steam.auth.wait_for_qr_approval(qr_session(interval=2))

    assert [form_of(r)["client_id"] for r in fake_steam.requests] == [
        CLIENT_ID,
        "6097734395127281918",
        "6097734395127281918",
    ]
    assert clock.sleeps == [2.0, 2.0]


async def test_wait_times_out_after_a_last_poll_at_the_deadline(
    steam: Steam, fake_steam: FakeSteam, clock: VirtualClock
) -> None:
    fake_steam.api("POST", POLL_PATH, json=PENDING)

    with pytest.raises(TimeoutError, match="not approved within 12 seconds"):
        await steam.auth.wait_for_qr_approval(qr_session(), timeout=12)

    # Polls at 0, 5, 10 and 12 seconds; the last sleep stops at the deadline.
    assert clock.sleeps == [5.0, 5.0, 2.0]
    assert len(fake_steam.requests) == 4
    assert clock.now == 1012.0


async def test_wait_uses_five_seconds_when_steam_sends_no_interval(
    steam: Steam, fake_steam: FakeSteam, clock: VirtualClock
) -> None:
    fake_steam.api("POST", POLL_PATH, json=PENDING)
    fake_steam.api("POST", POLL_PATH, json=APPROVED)

    await steam.auth.wait_for_qr_approval(qr_session(interval=0))

    assert clock.sleeps == [5.0]


async def test_wait_raises_poll_errors(
    steam: Steam, fake_steam: FakeSteam, clock: VirtualClock
) -> None:
    fake_steam.api("POST", POLL_PATH, json=PENDING)
    # An expired session: one client reports HTTP 500 "Transport error 2".
    fake_steam.api("POST", POLL_PATH, text="Transport error 2", status=500)

    with pytest.raises(SteamAPIError) as excinfo:
        await steam.auth.wait_for_qr_approval(qr_session())

    assert excinfo.value.status_code == 500
    assert len(fake_steam.requests) == 2
    assert clock.sleeps == [5.0]


@pytest.mark.parametrize("timeout", [0, -1, True, "60", float("nan")])
async def test_wait_rejects_bad_timeout_before_any_request(
    steam: Steam, fake_steam: FakeSteam, clock: VirtualClock, timeout: Any
) -> None:
    with pytest.raises(ValueError, match="timeout must be a positive number"):
        await steam.auth.wait_for_qr_approval(qr_session(), timeout=timeout)

    assert fake_steam.requests == []


async def test_wait_rejects_session_without_ids_before_any_request(
    steam: Steam, fake_steam: FakeSteam, clock: VirtualClock
) -> None:
    with pytest.raises(ValueError, match="Invalid client id"):
        await steam.auth.wait_for_qr_approval(QRAuthSession())

    assert fake_steam.requests == []


# -- redirects and misplaced arguments -------------------------------------------


@pytest.mark.parametrize("status", [301, 302, 307, 308])
@endpoint_params(ENDPOINTS)
async def test_redirect_is_not_followed(
    steam: Steam,
    fake_steam: FakeSteam,
    caplog: pytest.LogCaptureFixture,
    endpoint: Endpoint,
    status: int,
) -> None:
    # aiohttp would POST the body (refresh token, request_id) again to a 307 or
    # 308 target, and take a 301/302 target's reply as Steam's.
    caplog.set_level(logging.DEBUG)
    elsewhere = "/elsewhere/"
    endpoint.serve(
        fake_steam, status=status, headers={"Location": fake_steam.url + elsewhere}
    )
    for verb in ("GET", "POST"):
        fake_steam.api(verb, elsewhere, json=endpoint.reply)

    with pytest.raises(SteamAPIError) as excinfo:
        await endpoint.call(steam)

    assert excinfo.value.status_code == status
    assert [r.path for r in fake_steam.requests] == [endpoint.path]
    texts = (str(excinfo.value), repr(excinfo.value), caplog.text)
    assert_no_secret_in(*texts)
    assert_no_secret_in(*texts, secrets=[REQUEST_ID])


@pytest.mark.parametrize(
    "steamid",
    [
        pytest.param(REFRESH_TOKEN, id="refresh-token-in-steamid-place"),
        pytest.param(POLL_REFRESH, id="other-token"),
    ],
)
async def test_generate_with_swapped_arguments_does_not_echo_the_token(
    steam: Steam,
    fake_steam: FakeSteam,
    caplog: pytest.LogCaptureFixture,
    steamid: str,
) -> None:
    # The library's other methods take the Steam ID first, so a caller may
    # well pass (steamid, refresh_token).
    caplog.set_level(logging.DEBUG)

    with pytest.raises(InvalidSteamIDError, match="Invalid Steam ID") as excinfo:
        await steam.auth.generate_access_token_for_app(STEAMID, steamid)

    assert fake_steam.requests == []
    error = excinfo.value
    assert error.__context__ is None
    assert_no_secret_in(str(error), repr(error), str(error.steamid), caplog.text)


async def test_poll_with_swapped_ids_does_not_echo_the_request_id(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    with pytest.raises(ValueError, match="Invalid client id") as excinfo:
        await steam.auth.poll_auth_session_status(REQUEST_ID, CLIENT_ID)

    assert fake_steam.requests == []
    assert_no_secret_in(str(excinfo.value), secrets=[REQUEST_ID])
