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

- The API is grouped into the namespaces planned in [#25]: `Steam.users`
  (was `player`), `Steam.library` (owned games), `Steam.store` (app
  details, the app list, game search and news), `Steam.stats` (now also
  achievements and schemas), `Steam.economy` (inventories), `Steam.market`,
  `Steam.family`, and the new `Steam.friends`, `Steam.wishlist`,
  `Steam.workshop` and `Steam.util` ([#15], [#25]).
- **Deprecated:** `Steam.player` (use `Steam.users`; `PlayerAPI` is now an
  alias of `UsersAPI`), `Steam.games` / `GameAPI` (use `Steam.library`,
  `Steam.store` and `Steam.stats`), `StatsAPI.get_news_for_app()` (use
  `Steam.store`) and `MarketAPI`'s inventory methods (use `Steam.economy`).
  They still work and raise `DeprecationWarning` ([#15], [#25]).
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
- **Breaking:** Client-side rate limiting is per Steam host (Web API, store,
  community), as a token bucket with a burst. Defaults: Web API 1 request/s
  (burst 10; Steam allows 100,000 calls a day per key), store 0.5/s (burst
  10), community 0.25/s (burst 5). `REQUESTS_PER_SECOND` (previously one
  10/s limit for everything) is replaced by `API_/STORE_/COMMUNITY_`
  `REQUESTS_PER_SECOND` and `_BURST` ([#24]).
- **Breaking:** `Steam()` no longer requires a credential; methods that need
  one raise `AuthenticationError` when it is missing ([#24]).
- Endpoints send only the credential they need: `get_current_players()`,
  `get_news_for_app()`, `get_global_achievement_percentages()` and
  `get_global_stats_for_game()` send none, and `get_owned_games()` and the
  app list use the access token when there is no API key ([#24]).
- **Breaking:** `MarketAPI.get_price_history()` needs the `steamLoginSecure`
  cookie (`Steam(steam_login_secure=...)`) and raises `AuthenticationError`
  without it, or when Steam rejects it (HTTP 400 `[]` or a redirect to the
  login page); Steam refuses anonymous calls ([#22], [#24]).
- `repr(Steam(...))` lists only the credentials that are set, masked
  ([#24]).
- POST inputs are sent as a form body; repeated fields are sent as
  `name[0]=…&name[1]=…` (`appids_filter`, `request_ids`) ([#18]).
- `Client.request()` reconnects after `close()` ([#10]).
- Family API calls re-raise library exceptions unchanged and wrap model
  validation errors in `ResponseParsingError`; error messages name the right
  operation ([#10], [#14]).
- **Breaking:** `FamilyAPI.request_purchase()` takes `gid_shopping_cart`
  (was `gid_shopping_card`) and sends it as `gidshoppingcart`; the cart id
  was silently dropped before ([#19]).
- **Breaking:** `FamilyAPI.get_playtime_summary()` returns
  `PlaytimeSummaryResponse`; the `SteamResponse`, `Entry` and `ResponseData`
  classes in `steamy_py.models.family` are renamed to
  `PlaytimeSummaryResponse`, `PlaytimeEntry` and `PlaytimeSummary` ([#14]).
- Family models are based on `SteamModel` and exported from
  `steamy_py.models` ([#14]).
- **Breaking:** Family read methods return models instead of raw dicts:
  `get_family_group()` → `FamilyGroupResponse`, `get_change_log()` →
  `FamilyGroupChangeLogResponse`, `get_preferred_lenders()` →
  `PreferredLendersResponse`, `get_purchase_requests()` →
  `PurchaseRequestsResponse`, `get_invite_check_results()` →
  `InviteCheckResultsResponse`, `get_users_sharing_device()` →
  `UsersSharingDeviceResponse` ([#1], [#14]).
- `FamilyAPI.get_purchase_requests()`: `request_ids` is optional ([#19]).
- Support-only Family methods (`force_accept_invite`, `clear_cooldown_skip`,
  `set_family_cooldown_overrides`, `rollback_family_group`,
  `undelete_family_group`) are documented as such ([#19]).
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
- **Breaking:** `MarketAPI.get_market_listings()` returns the new
  `MarketListingsResponse` shape (`listinginfo`, `assets`, `currency`);
  `search_market()` and `get_popular_items()` return `MarketSearchResponse`
  (the previous fields, `searchdata` and `results`) ([#22]).
- **Breaking:** `StatsAPI.get_user_achievements_only()` calls
  `GetPlayerAchievements`, so it returns locked achievements too, with
  unlock times ([#20]).
- **Breaking:** `get_news_for_app()` no longer caps `count` at 20 ([#20]).
- **Breaking:** `GetFriendList` answering HTTP 401 (a private friends list)
  raises `PrivateProfileError` instead of `AuthenticationError` ([#20]).
- **Breaking:** `GlobalAchievementResponse` holds the parsed list in
  `achievements`, and `GlobalStatsResponse.globalstats` maps each stat to
  `GlobalStatTotal` ([#20]).
- `resolve_vanity_url()` returns the Steam ID of a `/profiles/<id>` URL
  without a request ([#20]); an invalid ID in such a URL raises
  `InvalidSteamIDError` ([#23]).
- Methods that take a Steam ID accept an `int`, a string or a `SteamID`
  ([#23]); Family methods validate them before sending ([#15]).
- Family methods accept 64-bit ids (family group, invite, nonce, cart,
  request) as `int` or `str`, send `0` instead of silently dropping it, and
  are annotated with their return types ([#15]).
- A response that fails model validation raises `ResponseParsingError`
  (a `SteamAPIError` subclass) from every method, not only Family methods;
  so does a response missing its top-level object in the methods that check
  for it (e.g. `get_player_summaries()`, `get_owned_games()`) ([#15]).
- Repository methods no longer log every failure at ERROR level; the client
  still logs failed requests ([#15]).
- `aiohttp[speedups]` is now optional: install `steamy-py[speedups]` to get
  it ([#6]).
- `__version__` and the `User-Agent` header now report the installed package
  version ([#6]).
- **Breaking:** `Settings` no longer reads a `.env` file, and reads
  environment variables only with the `STEAMY_` prefix
  (`STEAMY_MAX_RETRIES`, not `MAX_RETRIES`). Field names are
  case-insensitive (`Steam(max_retries=5)`), and an unknown or invalid
  setting raises `ConfigurationError` from `Steam()` (`ValidationError` from
  `Settings()`) instead of being ignored ([#12]).
- `Steam(settings=..., MAX_RETRIES=5)` applies the keyword arguments on top
  of `settings`; they were silently dropped ([#12]).
- The library no longer configures logging: `Client()` does not call
  `logging.basicConfig()`, the `steamy_py` logger has a `NullHandler`, and
  connect/disconnect messages are logged at DEBUG, once ([#12]).
- **Breaking:** `GameAPI.get_app_list()` uses `IStoreService/GetAppList/v1`
  (Valve deprecated `ISteamApps/GetAppList/v2`) and pages through the list.
  It asks for games, DLC, software, videos and hardware by default and takes
  the endpoint's filters as keyword arguments. `AppListResponse` and
  `GetAppListResponse` have the new response shape ([#13]).
- `Steam.test_connection()` and `Steam.get_api_key_info()` call
  `ISteamWebAPIUtil/GetServerInfo` plus one small request with the
  configured credential (the access token when there is no key), instead of
  downloading the whole app list ([#13]).

### Added

- Milestone 1 endpoints from [#25]:
  - `Steam.users.get_badges()` and `get_steam_level()` (`IPlayerService`)
  - `Steam.library.get_recently_played_games()` and
    `get_last_played_times()` (`IPlayerService`; the latter with the access
    token)
  - `Steam.friends.get_friends_list()` (`IFriendsListService`, access token)
  - `Steam.store.get_items()` (`IStoreBrowseService/GetItems`),
    `search_suggestions()` (`IStoreQueryService/SearchSuggestions`) and
    `store_search()` (`store.steampowered.com/api/storesearch`)
  - `Steam.wishlist.get_wishlist()` and `get_wishlist_item_count()`
    (`IWishlistService`, no credential)
  - `Steam.workshop.get_details()`, `query_files()` and
    `iter_query_files()` (`IPublishedFileService`), and
    `get_published_file_details()` (`ISteamRemoteStorage`, no credential)
  - `Steam.util.get_server_info()` and `get_supported_api_list()`
    (`ISteamWebAPIUtil`, no credential)
- `Client(session=...)` / `Steam(session=...)` to reuse an existing aiohttp
  session (never closed by the library), and `Settings.CONNECTION_LIMIT`
  ([#10]).
- `SteamAPIError.eresult` ([#18]).
- `steam_login_secure` parameter (or `STEAM_LOGIN_SECURE` environment
  variable) and `auth_type="cookie"` for steamcommunity.com endpoints that
  need a login, and `auth_type="any"` (API key if set, else access token)
  ([#24]).
- `MarketAPI.iter_inventory_pages()` and `MarketAPI.get_full_inventory()`
  page through an inventory with `start_assetid` ([#22]).
- `Settings.API_KEY_DAILY_LIMIT`: stop sending requests with the API key
  after this many per UTC day (`RateLimitError`, not sent);
  `Client.api_key_requests_today` ([#24]).
- `SteamID` type: parses SteamID64, Steam2 (`STEAM_1:0:84901`), Steam3
  (`[U:1:169802]`) and `/profiles/<id>` URLs, and converts between them
  ([#23]).
- `GameAPI.get_app_list_page()` and `GameAPI.iter_app_list()`; `SteamApp`
  carries `last_modified` and `price_change_number` ([#13]).
- `include_family_group_response` parameter for
  `FamilyAPI.get_family_group_for_user()` ([#19]).
- Family models keep `pending_group_invites` and `family_group`
  (`FamilyGroup`) on the user's status, `entries_by_owner` on the playtime
  summary, and `owner_steamid` / `sort_as` on shared library apps; new
  `EFamilyGroupRole`, `EPurchaseRequestAction` and `EProtoAppType` enums
  ([#14]).
- `input_json` support and an `_indexed()` helper for repeated fields in
  `BaseAPI` ([#18]).
- Support for Python 3.10, 3.11 and 3.12 (the minimum was 3.13) ([#6]).
- `Settings.STEAM_COMMUNITY_BASE_URL` ([#11]).
- `currency` parameter for `MarketAPI.get_market_listings()` and `language`
  parameter for `MarketAPI.get_inventory()` ([#11]).
- Inventory models keep `actions` (CS2 inspect links), `owner_descriptions`,
  `owner_actions`, `market_actions`, restrictions and `asset_properties`
  ([#22]).
- `end_date`, `feeds` and `tags` parameters for
  `StatsAPI.get_news_for_app()` ([#20]).
- `include_extended_appinfo`, `include_free_sub`, `skip_unvetted_apps`,
  `include_family_licenses` and `language` parameters for
  `GameAPI.get_owned_games()` ([#21]).
- `OwnedGame` keeps `rtime_last_played` (and `last_played`),
  `playtime_deck_forever`, `playtime_disconnected`,
  `has_community_visible_stats`, `family_shared`, `capsule_filename`,
  `sort_as`, `has_workshop/market/dlc/leaderboards` and
  `content_descriptorids`; `AppDetails` keeps `dlc`, `packages`,
  descriptions, requirements, `metacritic`, `achievements` and more as
  optional fields ([#21]).
- `py.typed` marker, so type checkers use the package's annotations ([#6]).
- Test suite, CI workflow and Dependabot configuration ([#8], [#9]).
- README: working examples, the credential each endpoint needs, Steam's
  rate limits and terms, and thanks to xPaw ([#2], [#24]).

### Removed

- **Breaking:** Unused models `LeaderboardEntry`, `LeaderboardResponse`,
  `MarketSearch`, `PaginatedResponse`, `ErrorResponse`, `GameStat` and
  `GetUserStatsResponse`. `steamy_py.models.UserStatsResponse` is now the
  model `StatsAPI.get_user_stats_for_game()` returns; the
  `StatsUserStatsResponse` alias is gone ([#15]).
- `BaseAPI._get_request`, `_post_request`, `_put_request` and
  `_delete_request` ([#15]).
- **Breaking:** The `LOG_LEVEL` and `LOG_FORMAT` settings. An application
  with `LOG_LEVEL=info` in its environment crashed `Steam()` ([#12]).
- **Breaking:** `MarketAPI.get_recent_items()`. It sorted search results by
  quantity and never returned recently listed items ([#11]).
- **Breaking:** `OwnedGame.img_logo_url` and `OwnedGame.logo_url`. Steam no
  longer sends the logo hash ([#21]).
- The `dev` extra (`steamy-py[dev]`). Development tools are now a uv
  dependency group ([#6]).

### Fixed

- Steam ID validation accepts every individual account
  (`76561197960265729`–`76561202255233023`; IDs from `76561200000000000` up
  were rejected) and rejects IDs outside that range, group IDs and non-ASCII
  digits. App ID validation rejects `True`/`False`, which were sent as
  `appid=True` ([#23]).
- `MarketAPI.get_market_listings()` requested an HTML page; it now uses the
  `/market/listings/{appid}/{hash}/render/` JSON endpoint ([#22]).
- `MarketAPI.get_inventory()` failed on every non-empty inventory (`pos` is
  now optional) and on descriptions with nested `app_data`; a private
  inventory (HTTP 403) raises `PrivateProfileError` ([#22]).
- Price-to-cents conversion no longer truncates (`$0.29` was 28) and parses
  every currency format, not only `$` ([#22]).
- `MarketAPI.get_price_history()` no longer crashes on a non-object reply
  ([#22]).
- `MarketAPI.get_inventory()` asks for 2000 items by default (was 5000,
  above Steam's page size) ([#22]).
- `MarketAPI.get_item_price()` returns None for an unknown item (HTTP 500
  `{"success": false}`) ([#22]).
- `PlayerAPI.get_player_bans()` failed on every response: `PlayerBan` now
  reads Steam's PascalCase keys ([#20]).
- `get_global_achievement_percentages()` and `get_global_stats_for_game()`
  failed on every real response; an unknown app raises `GameNotFoundError`
  for global stats and `get_current_players()` instead of a validation
  error ([#20]).
- `resolve_vanity_url()` sent an empty vanity name for a URL with a trailing
  slash ([#20]).
- `GameAPI.get_player_achievements()` maps a private profile (HTTP 403) to
  `PrivateProfileError` and an app without stats (HTTP 400) to
  `GameNotFoundError` ([#21]).
- `GameAPI.get_schema_for_game()` raises `GameNotFoundError` for an app
  without a schema (`{"game": {}}`); `gameName`, `gameVersion` and
  `SchemaAchievement.description` are optional ([#21]).
- `GameAPI.get_app_details()` returns None for a JSON `null` body instead of
  crashing ([#21]).
- `GameAPI.search_games(owned_games=[])` no longer downloads the full app
  list ([#21]).
- `OwnedGame.icon_url` uses https ([#21]).
- Project URLs in the package metadata pointed to the wrong repository
  ([#6]).
- `FamilyAPI.resend_invitation_to_family_group()` called
  `RespondToRequestedPurchase` and `rollback_family_group()` called
  `SetFamilyCooldownOverrides`; both now call their own method ([#19]).
- `FamilyAPI.get_change_log()` uses POST, as Steam documents ([#19]).
- Family models no longer fail when Steam omits fields at their default
  value, e.g. for a user outside any family, an empty shared library or an
  empty playtime summary ([#14]).

[Unreleased]: https://github.com/AuthFailed/steamy-py/compare/ba78383...main
[#1]: https://github.com/AuthFailed/steamy-py/issues/1
[#2]: https://github.com/AuthFailed/steamy-py/issues/2
[#6]: https://github.com/AuthFailed/steamy-py/issues/6
[#8]: https://github.com/AuthFailed/steamy-py/issues/8
[#10]: https://github.com/AuthFailed/steamy-py/issues/10
[#9]: https://github.com/AuthFailed/steamy-py/issues/9
[#11]: https://github.com/AuthFailed/steamy-py/issues/11
[#12]: https://github.com/AuthFailed/steamy-py/issues/12
[#13]: https://github.com/AuthFailed/steamy-py/issues/13
[#14]: https://github.com/AuthFailed/steamy-py/issues/14
[#15]: https://github.com/AuthFailed/steamy-py/issues/15
[#17]: https://github.com/AuthFailed/steamy-py/issues/17
[#18]: https://github.com/AuthFailed/steamy-py/issues/18
[#19]: https://github.com/AuthFailed/steamy-py/issues/19
[#20]: https://github.com/AuthFailed/steamy-py/issues/20
[#21]: https://github.com/AuthFailed/steamy-py/issues/21
[#22]: https://github.com/AuthFailed/steamy-py/issues/22
[#23]: https://github.com/AuthFailed/steamy-py/issues/23
[#24]: https://github.com/AuthFailed/steamy-py/issues/24
[#25]: https://github.com/AuthFailed/steamy-py/issues/25
