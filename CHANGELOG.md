# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work towards 2.0.0 — see the [roadmap](https://github.com/AuthFailed/steamy-py/issues/16).

### Security

- The Steam Web API key and access token no longer appear in log messages,
  exception messages or exception chains. aiohttp errors embed the full
  request URL, including credentials; the client now raises sanitized
  library exceptions instead ([#17]).
- Steam Community market and inventory requests no longer send the Web API
  key to steamcommunity.com ([#11]).
- `Client.request()` no longer writes the API key or access token into the
  caller's `params` dict, so a reused dict no longer carries credentials into
  later requests ([#17]).

### Changed

- **Breaking:** `Client.request()` raises library exceptions instead of
  aiohttp errors: `SteamAPIError` (with `status_code`) for HTTP errors,
  `NetworkError` for connection errors, `RateLimitError` when every attempt
  was rate limited, and `ResponseParsingError` (previously `ValueError`) for
  invalid JSON ([#17]). When attempts fail in different ways, the last error
  that was not a rate limit is raised.
- `Client.request()` accepts `params` as a mapping, a `MultiDict` or a list
  of `(key, value)` pairs and keeps repeated keys; a string is rejected with
  `TypeError`.
- **Breaking:** `MarketAPI.search_market()` no longer adds Counter-Strike 2
  `category_730_*` filters whenever an app id is given ([#11]).
- **Breaking:** `MarketAPI.market_base_url` is now a read-only property
  derived from the new `Settings.STEAM_COMMUNITY_BASE_URL` ([#11]).
- `aiohttp[speedups]` is now optional: install `steamy-py[speedups]` to get
  it ([#6]).
- `__version__` and the `User-Agent` header now report the installed package
  version ([#6]).

### Added

- Support for Python 3.10, 3.11 and 3.12 (the minimum was 3.13) ([#6]).
- `Settings.STEAM_COMMUNITY_BASE_URL` ([#11]).
- `currency` parameter for `MarketAPI.get_market_listings()` and `language`
  parameter for `MarketAPI.get_inventory()` ([#11]).
- `py.typed` marker, so type checkers use the package's annotations ([#6]).
- Test suite, CI workflow and Dependabot configuration ([#8], [#9]).

### Removed

- **Breaking:** `MarketAPI.get_recent_items()`. It sorted search results by
  quantity and never returned recently listed items ([#11]).
- The `dev` extra (`steamy-py[dev]`). Development tools are now a uv
  dependency group ([#6]).

### Fixed

- Project URLs in the package metadata pointed to the wrong repository
  ([#6]).

[Unreleased]: https://github.com/AuthFailed/steamy-py/compare/ba78383...main
[#6]: https://github.com/AuthFailed/steamy-py/issues/6
[#8]: https://github.com/AuthFailed/steamy-py/issues/8
[#9]: https://github.com/AuthFailed/steamy-py/issues/9
[#11]: https://github.com/AuthFailed/steamy-py/issues/11
[#17]: https://github.com/AuthFailed/steamy-py/issues/17
