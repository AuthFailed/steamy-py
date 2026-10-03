"""Steam ID and app ID validation.

A SteamID64 packs four fields into 64 bits::

    universe (8 bits) | account type (4) | instance (20) | account id (32)

Every method of this library that takes a user's Steam ID expects an
individual account in the public universe (universe 1, type 1, instance 1),
which leaves ``76561197960265729 <= steamid <= 76561202255233023``.
"""

from __future__ import annotations

import re
from typing import TypeAlias

from .exceptions import InvalidAppIDError, InvalidSteamIDError

# SteamID64 of account id 0: universe Public, type Individual, instance Desktop.
INDIVIDUAL_BASE = (1 << 56) | (1 << 52) | (1 << 32)
ACCOUNT_ID_MAX = 2**32 - 1
STEAMID64_MIN = INDIVIDUAL_BASE + 1
STEAMID64_MAX = INDIVIDUAL_BASE + ACCOUNT_ID_MAX

APP_ID_MAX = 2**32 - 1

_DIGITS_RE = re.compile(r"[0-9]+", re.ASCII)
_STEAM2_RE = re.compile(r"STEAM_[01]:([01]):([0-9]+)", re.ASCII)
_STEAM3_RE = re.compile(r"\[U:1:([0-9]+)\]|U:1:([0-9]+)", re.ASCII)
_PROFILE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?steamcommunity\.com/profiles/([0-9]+)/?",
    re.ASCII | re.IGNORECASE,
)


class SteamID:
    """The Steam ID of an individual account.

    ``SteamID(value)`` takes a SteamID64 as an ``int`` or a string of ASCII
    digits; ``SteamID.parse`` also understands the Steam2 (``STEAM_1:0:84901``)
    and Steam3 (``[U:1:169802]``) forms and ``/profiles/<id>`` URLs. Every
    method that takes a Steam ID accepts a ``SteamID`` too.

    Example:
        ```python
        steamid = SteamID.parse("[U:1:169802]")
        str(steamid)       # "76561197960435530"
        steamid.steam2     # "STEAM_1:0:84901"
        steamid.account_id  # 169802
        ```

    Raises:
        InvalidSteamIDError: If the value is not an individual account's ID
    """

    __slots__ = ("_value",)

    def __init__(self, value: SteamIDLike) -> None:
        self._value = _parse_steamid64(value)

    @classmethod
    def from_account_id(cls, account_id: int) -> SteamID:
        """The SteamID of the individual account with ``account_id``."""
        if (
            isinstance(account_id, bool)
            or not isinstance(account_id, int)
            or not 0 < account_id <= ACCOUNT_ID_MAX
        ):
            raise InvalidSteamIDError(
                str(account_id), f"Invalid account id: {account_id!r}"
            )
        return cls(INDIVIDUAL_BASE + account_id)

    @classmethod
    def parse(cls, value: SteamIDLike) -> SteamID:
        """Parse a SteamID64, Steam2 or Steam3 ID, or a ``/profiles/`` URL."""
        if isinstance(value, str):
            text = value.strip()
            if match := _STEAM2_RE.fullmatch(text):
                low_bit, half = int(match[1]), int(match[2])
                return cls._from_account_id_text(value, half * 2 + low_bit)
            if match := _STEAM3_RE.fullmatch(text):
                return cls._from_account_id_text(value, int(match[1] or match[2]))
            if match := _PROFILE_URL_RE.fullmatch(text):
                text = match[1]
            return cls(text)
        return cls(value)

    @classmethod
    def _from_account_id_text(cls, original: str, account_id: int) -> SteamID:
        if not 0 < account_id <= ACCOUNT_ID_MAX:
            raise InvalidSteamIDError(original, f"Invalid Steam ID: {original!r}")
        return cls(INDIVIDUAL_BASE + account_id)

    @property
    def account_id(self) -> int:
        """The 32-bit account id (the Steam3 number)."""
        return self._value - INDIVIDUAL_BASE

    @property
    def steam2(self) -> str:
        """The Steam2 form, e.g. ``STEAM_1:0:84901``."""
        account_id = self.account_id
        return f"STEAM_1:{account_id & 1}:{account_id >> 1}"

    @property
    def steam3(self) -> str:
        """The Steam3 form, e.g. ``[U:1:169802]``."""
        return f"[U:1:{self.account_id}]"

    @property
    def profile_url(self) -> str:
        """The community profile URL."""
        return f"https://steamcommunity.com/profiles/{self._value}/"

    def __int__(self) -> int:
        return self._value

    def __str__(self) -> str:
        return str(self._value)

    def __repr__(self) -> str:
        return f"SteamID({self._value})"

    def __eq__(self, other: object) -> bool:
        if isinstance(other, SteamID):
            return self._value == other._value
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)


SteamIDLike: TypeAlias = int | str | SteamID


def _parse_steamid64(value: object) -> int:
    """The SteamID64 of an individual account, or ``InvalidSteamIDError``."""
    if isinstance(value, SteamID):
        return int(value)
    if isinstance(value, bool) or not isinstance(value, int | str):
        raise InvalidSteamIDError(
            str(value), f"Steam ID must be an int or a string, not {value!r}"
        )
    if isinstance(value, str):
        if not value:
            raise InvalidSteamIDError(value, "Steam ID cannot be empty")
        if not _DIGITS_RE.fullmatch(value):
            raise InvalidSteamIDError(
                value, f"Steam ID must be a SteamID64 of ASCII digits: {value!r}"
            )
        number = int(value)
    else:
        number = value
    if not STEAMID64_MIN <= number <= STEAMID64_MAX:
        raise InvalidSteamIDError(
            str(value), f"Not the SteamID64 of an individual account: {value!r}"
        )
    return number


def validate_steam_id(value: SteamIDLike) -> str:
    """Check an individual account's SteamID64 and return it as a string.

    Accepts an ``int``, a string of ASCII digits or a ``SteamID``.

    Raises:
        InvalidSteamIDError: If ``value`` is not an individual account's
            SteamID64
    """
    return str(_parse_steamid64(value))


def validate_app_id(value: int) -> int:
    """Check an app id (a positive 32-bit ``int``, not a ``bool``) and return it.

    Raises:
        InvalidAppIDError: If ``value`` is not a valid app id
    """
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 < value <= APP_ID_MAX
    ):
        raise InvalidAppIDError(str(value), "App ID must be a positive integer")
    return value
