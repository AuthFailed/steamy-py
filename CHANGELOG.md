# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Work towards 2.0.0 — see the [roadmap](https://github.com/AuthFailed/steamy-py/issues/16).

### Security

- Requests that carry the API key or access token no longer follow redirects,
  and POST requests send the credential in the form body instead of the URL
  ([#10], [#18]).
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

- **Breaking:** A missing API key or access token raises `AuthenticationError`
  (previously `ValueError`) ([#10]).
- **Breaking:** HTTP errors raise specific exceptions: `AuthenticationError`
  for 401/403 on requests that carry a credential, `ServiceUnavailableError`
  for 502/503/504, `SteamAPIError` otherwise. Every error keeps the response
  body in `response_data` ([#10]).
- **Breaking:** Service-method failures reported through the `x-eresult`
  header (HTTP 200 with an empty response) now raise instead of returning
  `{"response": {}}`: `AuthenticationError` (e.g. AccessDenied),
  `RateLimitError` (RateLimitExceeded), `ServiceUnavailableError` (Busy,
  ServiceUnavailable) or `SteamAPIError`, with the code in `eresult` ([#18]).
- Retries: 4xx responses are never retried; POST requests are retried only
  when Steam did not process them (connection failures, rate limits);
  timeouts become `NetworkError` and are retried for GET. `Retry-After` is
  honoured in seconds or as an HTTP date, never waited out after the last
  attempt, capped by `Settings.MAX_RETRY_WAIT`, and exposed as
  `RateLimitError.retry_after` ([#10]).
- The client-side rate limiter reserves a slot per request, so concurrent
  requests are spaced out ([#10]).
- POST inputs are sent as a form body; repeated fields are sent as
  `name[0]=…&name[1]=…` (`appids_filter`, `request_ids`) ([#18]).
- `Client.request()` reconnects after `close()` ([#10]).
- Family API calls re-raise library exceptions unchanged and wrap model
  validation errors in `SteamAPIError`; error messages name the right
  operation ([#10]).
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

- `Client(session=...)` / `Steam(session=...)` to reuse an existing aiohttp
  session (never closed by the library), and `Settings.CONNECTION_LIMIT`
  ([#10]).
- `SteamAPIError.eresult` ([#18]).
- `input_json` support and an `_indexed()` helper for repeated fields in
  `BaseAPI` ([#18]).
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
[#10]: https://github.com/AuthFailed/steamy-py/issues/10
[#9]: https://github.com/AuthFailed/steamy-py/issues/9
[#11]: https://github.com/AuthFailed/steamy-py/issues/11
[#17]: https://github.com/AuthFailed/steamy-py/issues/17
[#18]: https://github.com/AuthFailed/steamy-py/issues/18
