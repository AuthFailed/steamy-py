"""Packaging checks: version, typing marker, public exports and default settings."""

from __future__ import annotations

import importlib.metadata
import importlib.resources
import logging
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import steamy_py
import steamy_py.models
import steamy_py.repos
from steamy_py import Settings, Steam, SteamAPIError, __version__
from tests.fakesteam import FakeSteam

PROJECT_ROOT = Path(__file__).resolve().parents[1]

PUBLIC_MODULES = [steamy_py, steamy_py.models, steamy_py.repos]

# Variables ``Settings`` reads from the environment.
SETTINGS_ENV_VARS = tuple(f"STEAMY_{name}" for name in Settings.model_fields)


@pytest.fixture
def clean_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Run from an empty directory with no ``Settings`` variables set."""
    for name in SETTINGS_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def module_id(module: ModuleType) -> str:
    return module.__name__


# -- version -------------------------------------------------------------------


def test_version_matches_the_installed_distribution() -> None:
    assert __version__ == importlib.metadata.version("steamy-py")


def test_version_matches_pyproject() -> None:
    tomllib = pytest.importorskip("tomllib")
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text("utf-8"))

    assert __version__ == pyproject["project"]["version"]


async def test_user_agent_reports_the_version(
    steam: Steam, fake_steam: FakeSteam
) -> None:
    fake_steam.api("GET", "/ISteamWebAPIUtil/GetServerInfo/v1/", json={})

    await steam.client.request(
        "GET", fake_steam.url + "/ISteamWebAPIUtil/GetServerInfo/v1/", auth_type="none"
    )

    assert fake_steam.last.headers["User-Agent"] == f"steamy-py/{__version__}"


# -- distribution contents -----------------------------------------------------


def test_py_typed_marker_is_shipped() -> None:
    marker = importlib.resources.files("steamy_py") / "py.typed"

    assert marker.is_file()


# -- public API ----------------------------------------------------------------


@pytest.mark.parametrize("module", PUBLIC_MODULES, ids=module_id)
def test_every_name_in_all_exists(module: ModuleType) -> None:
    missing = [name for name in module.__all__ if not hasattr(module, name)]

    assert missing == []


@pytest.mark.parametrize("module", PUBLIC_MODULES, ids=module_id)
def test_star_import_exports_exactly_all(module: ModuleType) -> None:
    namespace: dict[str, Any] = {}

    exec(f"from {module.__name__} import *", namespace)

    namespace.pop("__builtins__")
    assert sorted(namespace) == sorted(module.__all__)


@pytest.mark.parametrize("module", PUBLIC_MODULES, ids=module_id)
def test_all_is_sorted_without_duplicates(module: ModuleType) -> None:
    assert module.__all__ == sorted(set(module.__all__))


def test_exported_exceptions_derive_from_steam_api_error() -> None:
    exceptions = [
        getattr(steamy_py, name) for name in steamy_py.__all__ if name.endswith("Error")
    ]

    assert SteamAPIError in exceptions
    assert all(issubclass(exc, SteamAPIError) for exc in exceptions)
    assert issubclass(SteamAPIError, Exception)


# -- settings ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("STEAM_API_BASE_URL", "https://api.steampowered.com"),
        ("STEAM_STORE_BASE_URL", "https://store.steampowered.com/api"),
        ("STEAM_COMMUNITY_BASE_URL", "https://steamcommunity.com"),
        ("REQUEST_TIMEOUT", 30),
        ("MAX_RETRIES", 3),
        ("RETRY_DELAY", 1.0),
        ("RATE_LIMIT_ENABLED", True),
        ("REQUESTS_PER_SECOND", 10.0),
    ],
)
def test_settings_defaults(clean_config: Path, field: str, expected: object) -> None:
    assert getattr(Settings(), field) == expected


def test_settings_ignore_the_applications_dotenv_file(clean_config: Path) -> None:
    baseline = Settings()
    (clean_config / ".env").write_text("MAX_RETRIES=0\nREQUEST_TIMEOUT=1\n")

    settings = Settings()

    assert (settings.MAX_RETRIES, settings.REQUEST_TIMEOUT) == (
        baseline.MAX_RETRIES,
        baseline.REQUEST_TIMEOUT,
    )


@pytest.mark.parametrize(
    ("name", "value"), [("MAX_RETRIES", "0"), ("REQUEST_TIMEOUT", "1")]
)
def test_settings_ignore_generic_environment_variables(
    clean_config: Path, monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    baseline = getattr(Settings(), name)
    monkeypatch.setenv(name, value)

    assert getattr(Settings(), name) == baseline


def test_settings_read_prefixed_environment_variables(
    clean_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STEAMY_MAX_RETRIES", "0")

    assert Settings().MAX_RETRIES == 0


def test_settings_no_longer_carry_logging_options(clean_config: Path) -> None:
    assert "LOG_LEVEL" not in Settings.model_fields
    assert "LOG_FORMAT" not in Settings.model_fields


def test_the_package_logger_has_only_a_null_handler() -> None:
    handlers = logging.getLogger("steamy_py").handlers

    assert [type(h) for h in handlers] == [logging.NullHandler]
