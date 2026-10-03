"""Smoke tests against the real Steam Web API.

Skipped by default. Run with ``STEAM_LIVE_API_KEY=... uv run pytest -m live``
(``STEAM_API_KEY`` works too).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest

from steamy_py import Steam

pytestmark = pytest.mark.live

# Gabe Newell's public profile.
PUBLIC_STEAMID = "76561197960287930"
COUNTER_STRIKE_2 = 730

# Read at import time: the autouse fixture in conftest.py removes STEAM_API_KEY
# from the environment before each test runs.
LIVE_API_KEY = os.environ.get("STEAM_LIVE_API_KEY") or os.environ.get("STEAM_API_KEY")


@pytest.fixture
async def live_steam() -> AsyncIterator[Steam]:
    if not LIVE_API_KEY:
        pytest.skip("set STEAM_LIVE_API_KEY (or STEAM_API_KEY) to run live tests")
    async with Steam(api_key=LIVE_API_KEY) as steam:
        yield steam


async def test_get_player_summary(live_steam: Steam) -> None:
    summary = await live_steam.users.get_player_summary(PUBLIC_STEAMID)
    assert summary is not None
    assert summary.steamid == PUBLIC_STEAMID


async def test_get_current_players(live_steam: Steam) -> None:
    count = await live_steam.stats.get_current_players(COUNTER_STRIKE_2)
    assert count.player_count > 0


async def test_get_news_for_app(live_steam: Steam) -> None:
    news = await live_steam.store.get_news_for_app(COUNTER_STRIKE_2, count=3)
    assert len(news) <= 3
