"""Authentication endpoints (steam.auth): QR sign-in and access tokens."""

from .base import BaseAPI


class AuthAPI(BaseAPI):
    """Sign-in and token helpers (IAuthenticationService)."""
