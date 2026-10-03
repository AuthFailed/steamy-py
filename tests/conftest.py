"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from steamy_py import Settings, Steam
from tests.fakesteam import (
    ACCESS_TOKEN,
    API_KEY,
    COMMUNITY_PREFIX,
    STORE_PREFIX,
    FakeSteam,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's real Steam credentials out of the tests."""
    monkeypatch.delenv("STEAM_API_KEY", raising=False)
    monkeypatch.delenv("STEAM_ACCESS_TOKEN", raising=False)


@pytest.fixture
async def fake_steam() -> AsyncIterator[FakeSteam]:
    """A running fake Steam server (see ``tests/fakesteam.py``)."""
    server = FakeSteam()
    await server.start()
    try:
        yield server
    finally:
        await server.close()


def make_settings(fake_steam: FakeSteam, **overrides: object) -> Settings:
    """Settings pointing every Steam host at ``fake_steam``.

    Rate limiting is off and retries are disabled unless overridden.
    """
    values: dict[str, object] = {
        "STEAM_API_BASE_URL": fake_steam.url,
        "STEAM_STORE_BASE_URL": fake_steam.url + STORE_PREFIX,
        "STEAM_COMMUNITY_BASE_URL": fake_steam.url + COMMUNITY_PREFIX,
        "RATE_LIMIT_ENABLED": False,
        "MAX_RETRIES": 0,
        "RETRY_DELAY": 0.0,
        "REQUEST_TIMEOUT": 5,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def settings(fake_steam: FakeSteam) -> Settings:
    """Settings for ``fake_steam`` with no retries and no rate limiting."""
    return make_settings(fake_steam)


@pytest.fixture
async def steam(settings: Settings) -> AsyncIterator[Steam]:
    """A connected ``Steam`` client with both an API key and an access token."""
    async with Steam(
        api_key=API_KEY, access_token=ACCESS_TOKEN, settings=settings
    ) as client:
        yield client
