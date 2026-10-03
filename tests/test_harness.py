"""Checks for the fake Steam server used by the test suite."""

from __future__ import annotations

from steamy_py import Steam
from tests.fakesteam import API_KEY, FakeSteam


async def test_routes_requests_and_records_them(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api(
        "GET", "/ISteamUser/GetPlayerSummaries/v2/", json={"response": {"players": []}}
    )

    data = await steam.client.request(
        "GET", f"{fake_steam.url}/ISteamUser/GetPlayerSummaries/v2/", params={"a": "1"}
    )

    assert data == {"response": {"players": []}}
    assert fake_steam.last.params == {"a": "1", "key": API_KEY}


async def test_replies_are_served_in_order_and_last_one_repeats(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    url = f"{fake_steam.url}/x"
    fake_steam.api("GET", "/x", json={"n": 1})
    fake_steam.api("GET", "/x", json={"n": 2})

    results = [
        await steam.client.request("GET", url, auth_type="none") for _ in range(3)
    ]

    assert [r["n"] for r in results] == [1, 2, 2]
