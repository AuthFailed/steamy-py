"""Authentication endpoints (steam.auth): QR sign-in and access tokens."""

import asyncio
import re
import time
from collections.abc import Mapping
from enum import IntEnum
from typing import Any, TypeVar

from pydantic import BaseModel

from ..exceptions import AuthenticationError, InvalidSteamIDError
from ..models.auth import (
    AppAccessToken,
    AppAccessTokenResponse,
    AuthSessionStatus,
    AuthSessionStatusResponse,
    EAuthTokenPlatformType,
    ETokenRenewalType,
    QRAuthSession,
    QRAuthSessionResponse,
)
from ..steamid import SteamIDLike, validate_steam_id
from .base import BaseAPI

_ModelT = TypeVar("_ModelT", bound=BaseModel)

_SERVICE = "IAuthenticationService"

_UINT32_MAX = 2**32 - 1
_UINT64_MAX = 2**64 - 1
_INT32_RANGE = range(-(2**31), 2**31)
_DIGITS_RE = re.compile(r"[0-9]{1,20}", re.ASCII)

# Seconds between polls when Steam sends no usable interval.
_DEFAULT_POLL_INTERVAL = 5.0

# Clock and sleep used by wait_for_qr_approval; tests replace them.
_monotonic = time.monotonic
_sleep = asyncio.sleep


def _uint64(value: object, what: str) -> str:
    """Check a positive 64-bit id (int, or its decimal string; not a bool)
    and return it as a decimal string.

    A bad string is not quoted in the error: it may be the ``request_id``
    passed in the wrong place.
    """
    number = value
    if isinstance(value, str) and _DIGITS_RE.fullmatch(value):
        number = int(value)
    if (
        isinstance(number, bool)
        or not isinstance(number, int)
        or not 0 < number <= _UINT64_MAX
    ):
        shown = (
            "a string that is not a positive 64-bit decimal id"
            if isinstance(value, str | bytes)
            else repr(value)
        )
        raise ValueError(f"Invalid {what}: {shown}")
    return str(int(number))


def _text(value: object, what: str) -> str:
    """Check a non-empty string input; the message never quotes the value."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{what} must be a non-empty string")
    return value


def _enum_value(value: object, enum: type[IntEnum], what: str) -> int:
    """Check a value of ``enum`` (a member or its int; not a bool)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Invalid {what}: {value!r}")
    try:
        return int(enum(value))
    except ValueError:
        raise ValueError(f"Invalid {what}: {value!r}") from None


def _int_in(value: object, allowed: range, what: str) -> int:
    """Check an int (not a bool) in ``allowed``."""
    if isinstance(value, bool) or not isinstance(value, int) or value not in allowed:
        raise ValueError(f"Invalid {what}: {value!r}")
    return value


def _token_owner_id(value: SteamIDLike) -> str:
    """Check the Steam ID that goes with a refresh token without echoing it.

    ``validate_steam_id`` quotes a bad value in its error; here that value may
    be the refresh token itself, passed in the wrong place.
    """
    try:
        return validate_steam_id(value)
    except InvalidSteamIDError:
        pass
    # Raised outside the except block so the original error, which quotes the
    # value, is not attached as __context__.
    raise InvalidSteamIDError(
        "<not shown>",
        f"Invalid Steam ID (a {type(value).__name__}; not shown in case it is "
        "the refresh token): expected the SteamID64 of the token's account",
    )


class AuthAPI(BaseAPI):
    """Sign-in and token helpers (IAuthenticationService).

    These methods never send the client's API key or access token: Steam
    needs neither for them. They are POST requests whose inputs go in the
    form body, so the refresh token given to ``generate_access_token_for_app``
    never appears in a URL, and they never follow a redirect, so neither it
    nor a ``request_id`` is sent anywhere but Steam. Returned tokens are kept
    out of ``repr()``, logs and exception messages; treat them like
    passwords.

    A QR sign-in::

        session = await steam.auth.begin_auth_session_via_qr()
        show_qr_code(session.challenge_url)  # scan with the Steam mobile app
        status = await steam.auth.wait_for_qr_approval(session)
        client = Steam(access_token=status.access_token)
    """

    async def _post(
        self,
        method: str,
        operation: str,
        model: type[_ModelT],
        *,
        inputs: Mapping[str, Any] | None = None,
        input_json: Mapping[str, Any] | None = None,
    ) -> _ModelT:
        """POST to an IAuthenticationService method without a credential.

        Like ``_call_service``, but a redirect is not followed: the body may
        hold a refresh token or ``request_id``, which aiohttp would send again
        to the redirect target (307/308), and a redirected reply could hand
        back a session or token that did not come from Steam. A redirect
        raises ``SteamAPIError`` instead.
        """
        with self._errors(operation):
            data = await self._request(
                _SERVICE,
                method,
                "v1",
                params=None if inputs is None else self._service_inputs(inputs),
                auth_type="none",
                http_method="POST",
                input_json=input_json,
                allow_redirects=False,
            )
            return model.model_validate(data)

    async def begin_auth_session_via_qr(
        self,
        *,
        device_friendly_name: str = "steamy-py",
        platform_type: int = EAuthTokenPlatformType.WEB_BROWSER,
        os_type: int | None = None,
        gaming_device_type: int | None = None,
        website_id: str | None = None,
    ) -> QRAuthSession:
        """Start a sign-in that the user approves by scanning a QR code.

        Calls IAuthenticationService/BeginAuthSessionViaQR (POST) without a
        credential. The device details go in ``device_details`` (as Steam's
        own web login sends them) and also as the top-level
        ``device_friendly_name`` and ``platform_type`` inputs Steam's API list
        documents, as one ``input_json`` form field.

        The platform type decides what the tokens are for: a ``WEB_BROWSER``
        sign-in gives tokens for the Web API and Steam websites (audience
        "web"); ``MOBILE_APP`` tokens can also be renewed with
        ``generate_access_token_for_app`` (as of 2025, per node-steam-session,
        Steam refuses that for web browser tokens). Steam may also check that
        a mobile-app sign-in comes from the mobile app (unverified); this
        method sends no app-specific headers.

        Args:
            device_friendly_name: Name the user sees for this sign-in, e.g. in
                the mobile app's approval prompt and the account's device list
            platform_type: ``EAuthTokenPlatformType``; Steam clients sign in
                over a Steam client (CM) connection, so ``STEAM_CLIENT`` over
                the Web API is unverified
            os_type: EOSType number for ``device_details``; left out when None
            gaming_device_type: Steam's gaming device type number for
                ``device_details``; left out when None
            website_id: Which Steam site the sign-in is for (e.g.
                "Community", "Store", "Mobile"); Steam uses "Unknown" when it
                is left out

        Returns:
            The session: ``challenge_url`` to show as a QR code, and the
            ``client_id``, ``request_id`` and ``interval`` to poll with

        Raises:
            ValueError: If an input is empty or out of range, or
                ``platform_type`` is not an ``EAuthTokenPlatformType``
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        name = _text(device_friendly_name, "device_friendly_name")
        platform = _enum_value(platform_type, EAuthTokenPlatformType, "platform_type")
        details: dict[str, object] = {
            "device_friendly_name": name,
            "platform_type": platform,
        }
        if os_type is not None:
            details["os_type"] = _int_in(os_type, _INT32_RANGE, "os_type")
        if gaming_device_type is not None:
            details["gaming_device_type"] = _int_in(
                gaming_device_type, range(_UINT32_MAX + 1), "gaming_device_type"
            )
        inputs: dict[str, object] = {
            "device_friendly_name": name,
            "platform_type": platform,
            "device_details": details,
        }
        if website_id is not None:
            inputs["website_id"] = _text(website_id, "website_id")
        result = await self._post(
            "BeginAuthSessionViaQR",
            "begin QR auth session",
            QRAuthSessionResponse,
            input_json=inputs,
        )
        return result.response

    async def poll_auth_session_status(
        self,
        client_id: int | str,
        request_id: str,
        token_to_revoke: int | str | None = None,
    ) -> AuthSessionStatus:
        """Check once whether the user approved a sign-in.

        Calls IAuthenticationService/PollAuthSessionStatus (POST) without a
        credential; ``request_id`` goes in the form body. Until the user
        approves, the status is empty (``had_remote_interaction`` turns true
        once the code is scanned); after approval it holds the tokens. When
        it has a ``new_client_id``, poll with that from then on.

        Steam answers an expired or unknown session with an error (one client
        reports HTTP 500; unverified), raised as ``SteamAPIError``.

        Args:
            client_id: The session's ``client_id`` (or the latest
                ``new_client_id``)
            request_id: The session's ``request_id``, as returned
            token_to_revoke: Id of one of the account's refresh tokens; Steam
                revokes it when the sign-in completes (unverified). Left out
                when None.

        Returns:
            The session status

        Raises:
            ValueError: If ``client_id`` or ``token_to_revoke`` is not a
                positive 64-bit id, or ``request_id`` is empty
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors
        """
        inputs = {
            "client_id": _uint64(client_id, "client id"),
            "request_id": _text(request_id, "request_id"),
            "token_to_revoke": (
                None
                if token_to_revoke is None
                else _uint64(token_to_revoke, "token id")
            ),
        }
        result = await self._post(
            "PollAuthSessionStatus",
            "poll auth session status",
            AuthSessionStatusResponse,
            inputs=inputs,
        )
        return result.response

    async def wait_for_qr_approval(
        self, session: QRAuthSession, *, timeout: float = 120.0
    ) -> AuthSessionStatus:
        """Poll a QR sign-in until the user approves it or ``timeout`` passes.

        Polls with ``poll_auth_session_status`` every ``session.interval``
        seconds (5 when Steam sent none), switching to ``new_client_id`` when
        Steam sends one. It cannot show a replacement ``new_challenge_url``;
        to redraw the QR code when Steam sends one, poll with
        ``poll_auth_session_status`` yourself.

        Args:
            session: The session from ``begin_auth_session_via_qr``
            timeout: Seconds to keep polling; the last poll happens at the
                deadline

        Returns:
            The approved status, with ``refresh_token`` and ``access_token``

        Raises:
            ValueError: If ``timeout`` is not a positive number, or the
                session has no valid ``client_id`` or ``request_id``
            TimeoutError: If the user did not approve within ``timeout``
            SteamAPIError: If a poll fails (e.g. the session expired)
        """
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, int | float)
            or not timeout > 0
        ):
            raise ValueError(f"timeout must be a positive number, not {timeout!r}")
        interval = session.interval if session.interval > 0 else _DEFAULT_POLL_INTERVAL
        deadline = _monotonic() + timeout
        client_id = session.client_id
        while True:
            status = await self.poll_auth_session_status(client_id, session.request_id)
            if status.new_client_id:
                client_id = status.new_client_id
            if status.is_approved:
                return status
            remaining = deadline - _monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"The QR sign-in was not approved within {timeout} seconds"
                )
            await _sleep(min(interval, remaining))

    async def generate_access_token_for_app(
        self,
        refresh_token: str,
        steamid: SteamIDLike,
        renewal_type: int | None = None,
    ) -> AppAccessToken:
        """Get a new access token for a refresh token; with
        ``renewal_type=ALLOW`` this may also replace the refresh token.

        Calls IAuthenticationService/GenerateAccessTokenForApp (POST). The
        refresh token is the credential: it goes in the form body, a redirect
        is not followed, and the client's API key and access token are not
        sent (published clients, e.g. node-steam-session, send none either).
        Mind the argument order: the refresh token comes first. An invalid
        ``steamid`` is reported without quoting it.

        As of 2025, per node-steam-session, Steam does this only for refresh
        tokens from a ``MOBILE_APP`` sign-in; for others it answers EResult
        AccessDenied, raised as ``AuthenticationError``. When Steam issues a
        new refresh token, the old one stops working: store the new one.

        Args:
            refresh_token: The refresh token
            steamid: Steam ID of the token's account (the token's ``sub``)
            renewal_type: ``ETokenRenewalType``; ``ALLOW`` lets Steam also
                issue a new refresh token. Left out when None (Steam's
                default is ``NONE``).

        Returns:
            ``access_token``, and ``refresh_token`` when Steam renewed it

        Raises:
            ValueError: If ``refresh_token`` is empty or ``renewal_type`` is
                not an ``ETokenRenewalType``
            InvalidSteamIDError: If the Steam ID is invalid
            AuthenticationError: If Steam refuses the refresh token, or
                answers without an access token
            ResponseParsingError: If the response does not fit the model
            SteamAPIError: On other API errors, or if Steam answers with a
                redirect
        """
        inputs = {
            "refresh_token": _text(refresh_token, "refresh_token"),
            "steamid": _token_owner_id(steamid),
            "renewal_type": (
                None
                if renewal_type is None
                else _enum_value(renewal_type, ETokenRenewalType, "renewal_type")
            ),
        }
        result = await self._post(
            "GenerateAccessTokenForApp",
            "generate access token",
            AppAccessTokenResponse,
            inputs=inputs,
        )
        tokens = result.response
        if not tokens.access_token:
            raise AuthenticationError(
                "Failed to generate access token: Steam returned no access token",
                status_code=None,
            )
        return tokens
