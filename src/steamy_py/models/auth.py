"""Models for IAuthenticationService: QR sign-in and access tokens.

The messages are ``CAuthentication_*`` in SteamDatabase/Protobufs
(steam/steammessages_auth.steamclient.proto). Steam may leave out any field at
its default value, so every field has a default. 64-bit ids (``client_id``)
arrive as strings; ``request_id`` is protobuf ``bytes`` and arrives
base64-encoded.

Tokens are secrets: the token fields are left out of ``repr()`` and ``str()``,
and validation errors never quote the response, so a malformed reply cannot
leak a token into a log or an exception message. ``model_dump()`` still
returns them.
"""

from enum import IntEnum

from pydantic import ConfigDict, Field

from .base import SteamModel


class EAuthTokenPlatformType(IntEnum):
    """What kind of client a sign-in is for; decides the tokens' audience."""

    UNKNOWN = 0
    STEAM_CLIENT = 1
    WEB_BROWSER = 2
    MOBILE_APP = 3


class EAuthSessionGuardType(IntEnum):
    """A way to confirm a sign-in (``confirmation_type``)."""

    UNKNOWN = 0
    NONE = 1
    EMAIL_CODE = 2
    DEVICE_CODE = 3
    DEVICE_CONFIRMATION = 4
    EMAIL_CONFIRMATION = 5
    MACHINE_TOKEN = 6
    LEGACY_MACHINE_AUTH = 7


class ETokenRenewalType(IntEnum):
    """Whether GenerateAccessTokenForApp may also issue a new refresh token."""

    NONE = 0
    ALLOW = 1


class _AuthModel(SteamModel):
    """Base for auth models: validation errors never show the input."""

    model_config = ConfigDict(hide_input_in_errors=True)


class AllowedConfirmation(_AuthModel):
    """A way the user can approve the sign-in."""

    confirmation_type: int = Field(
        default=EAuthSessionGuardType.UNKNOWN,
        description="``EAuthSessionGuardType``",
    )
    associated_message: str = ""


class QRAuthSession(_AuthModel):
    """A QR sign-in session (IAuthenticationService/BeginAuthSessionViaQR).

    Show ``challenge_url`` as a QR code for the Steam mobile app to scan, then
    poll with ``client_id`` and ``request_id`` every ``interval`` seconds.
    ``request_id`` is what lets a poller collect the tokens, so it is kept out
    of ``repr()``.
    """

    client_id: str = Field(default="", description="Session id (64-bit)")
    challenge_url: str = Field(
        default="", description="URL to show as a QR code (https://s.team/q/...)"
    )
    request_id: str = Field(
        default="", repr=False, description="Base64 polling secret; pass it back"
    )
    interval: float = Field(default=0.0, description="Seconds between polls")
    allowed_confirmations: list[AllowedConfirmation] = Field(default_factory=list)
    version: int = 0


class QRAuthSessionResponse(_AuthModel):
    """Response wrapper for IAuthenticationService/BeginAuthSessionViaQR."""

    response: QRAuthSession = Field(default_factory=QRAuthSession)


class AuthSessionStatus(_AuthModel):
    """One poll of a sign-in session (IAuthenticationService/PollAuthSessionStatus).

    Empty until the user approves; then ``refresh_token``, ``access_token``
    and ``account_name`` are set.
    """

    new_client_id: str = Field(
        default="", description="Replacement session id; poll with it from now on"
    )
    new_challenge_url: str = Field(
        default="", description="Replacement QR code URL, when Steam issues one"
    )
    refresh_token: str = Field(default="", repr=False, description="Secret")
    access_token: str = Field(default="", repr=False, description="Secret")
    had_remote_interaction: bool = Field(
        default=False, description="Whether the code was scanned"
    )
    account_name: str = Field(default="", description="Login name of the account")
    new_guard_data: str = Field(
        default="", repr=False, description="Steam Guard machine token (secret)"
    )
    agreement_session_url: str = ""

    @property
    def is_approved(self) -> bool:
        """Whether the sign-in is done (Steam sent a refresh token)."""
        return bool(self.refresh_token)


class AuthSessionStatusResponse(_AuthModel):
    """Response wrapper for IAuthenticationService/PollAuthSessionStatus."""

    response: AuthSessionStatus = Field(default_factory=AuthSessionStatus)


class AppAccessToken(_AuthModel):
    """Tokens from IAuthenticationService/GenerateAccessTokenForApp."""

    access_token: str = Field(default="", repr=False, description="Secret")
    refresh_token: str = Field(
        default="",
        repr=False,
        description="New refresh token (secret), only when Steam renewed it; "
        "the old one then stops working",
    )


class AppAccessTokenResponse(_AuthModel):
    """Response wrapper for IAuthenticationService/GenerateAccessTokenForApp."""

    response: AppAccessToken = Field(default_factory=AppAccessToken)
