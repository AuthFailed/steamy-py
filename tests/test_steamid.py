"""Tests for ``steamy_py.steamid``: the SteamID type and the ID validators."""

from __future__ import annotations

from typing import Any

import pytest

from steamy_py import InvalidAppIDError, InvalidSteamIDError, SteamID
from steamy_py.steamid import (
    INDIVIDUAL_BASE,
    STEAMID64_MAX,
    STEAMID64_MIN,
    validate_app_id,
    validate_steam_id,
)
from tests.fakesteam import STEAMID

ROBIN_ACCOUNT_ID = 169802


def test_individual_range_matches_steam_layout() -> None:
    assert INDIVIDUAL_BASE == 76561197960265728
    assert STEAMID64_MIN == 76561197960265729
    assert STEAMID64_MAX == 76561202255233023


@pytest.mark.parametrize(
    "value",
    [STEAMID, int(STEAMID), SteamID(STEAMID), str(STEAMID64_MIN), STEAMID64_MAX],
)
def test_validate_steam_id_returns_decimal_string(value: Any) -> None:
    assert validate_steam_id(value) == str(int(str(value)))


@pytest.mark.parametrize(
    "value",
    [
        "",
        True,
        None,
        7.6e16,
        STEAMID64_MIN - 1,
        STEAMID64_MAX + 1,
        f" {STEAMID}",
        "+" + STEAMID,
        STEAMID[:-1] + "\N{FULLWIDTH DIGIT ZERO}",
        "STEAM_1:0:84901",
    ],
)
def test_validate_steam_id_rejects(value: Any) -> None:
    with pytest.raises(InvalidSteamIDError) as excinfo:
        validate_steam_id(value)

    assert excinfo.value.steamid == str(value)


@pytest.mark.parametrize(
    "text",
    [
        STEAMID,
        "STEAM_0:0:84901",
        "STEAM_1:0:84901",
        "[U:1:169802]",
        "U:1:169802",
        f"https://steamcommunity.com/profiles/{STEAMID}/",
        f"steamcommunity.com/profiles/{STEAMID}",
        f"  {STEAMID}  ",
    ],
)
def test_parse_understands_every_form(text: str) -> None:
    assert SteamID.parse(text) == SteamID(STEAMID)


@pytest.mark.parametrize(
    "text",
    [
        "STEAM_2:0:84901",
        "STEAM_1:2:84901",
        "STEAM_1:0:0",
        "[U:1:0]",
        "[U:1:4294967296]",
        "[G:1:4]",
        "[U:1:169802",
        "https://steamcommunity.com/id/robinwalker/",
        "robinwalker",
    ],
)
def test_parse_rejects(text: str) -> None:
    with pytest.raises(InvalidSteamIDError):
        SteamID.parse(text)


def test_steamid_conversions() -> None:
    steamid = SteamID(STEAMID)

    assert int(steamid) == int(STEAMID)
    assert str(steamid) == STEAMID
    assert repr(steamid) == f"SteamID({STEAMID})"
    assert steamid.account_id == ROBIN_ACCOUNT_ID
    assert steamid.steam2 == "STEAM_1:0:84901"
    assert steamid.steam3 == "[U:1:169802]"
    assert steamid.profile_url == f"https://steamcommunity.com/profiles/{STEAMID}/"
    assert SteamID.from_account_id(ROBIN_ACCOUNT_ID) == steamid
    assert SteamID.parse(steamid.steam2) == steamid
    assert SteamID(steamid) == steamid


def test_steamid_odd_account_id_round_trips_through_steam2() -> None:
    steamid = SteamID.from_account_id(ROBIN_ACCOUNT_ID + 1)

    assert steamid.steam2 == "STEAM_1:1:84901"
    assert SteamID.parse(steamid.steam2) == steamid


def test_steamid_is_hashable_and_not_equal_to_other_types() -> None:
    steamid = SteamID(STEAMID)

    assert {steamid, SteamID(int(STEAMID))} == {steamid}
    assert steamid != STEAMID
    assert steamid != int(STEAMID)


@pytest.mark.parametrize("account_id", [0, -1, 2**32, True, "169802"])
def test_from_account_id_rejects(account_id: Any) -> None:
    with pytest.raises(InvalidSteamIDError):
        SteamID.from_account_id(account_id)


@pytest.mark.parametrize("app_id", [1, 440, 2**32 - 1])
def test_validate_app_id_accepts(app_id: int) -> None:
    assert validate_app_id(app_id) == app_id


@pytest.mark.parametrize("app_id", [0, -1, 2**32, True, False, "440", 440.0, None])
def test_validate_app_id_rejects(app_id: Any) -> None:
    with pytest.raises(InvalidAppIDError) as excinfo:
        validate_app_id(app_id)

    assert excinfo.value.app_id == str(app_id)
