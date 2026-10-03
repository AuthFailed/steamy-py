# steamy-py

Asynchronous Python wrapper for the Steam Web API, the Steam store API and
the Steam Community market, built on `aiohttp` and `pydantic`.

## Installation

Package is available on [PyPI](https://pypi.org/project/steamy-py/), you could install it with:

```bash
pip install steamy-py
```

or

```bash
uv add steamy-py
```

Install `steamy-py[speedups]` for aiohttp's optional C speedups.

## Quick start

```py
import asyncio

from steamy_py import Steam, SteamID


async def main():
    async with Steam(api_key="YOUR_API_KEY") as steam:
        # Any form of Steam ID works: SteamID64 (int or str), Steam2, Steam3,
        # or a /profiles/ URL through SteamID.parse().
        steamid = SteamID.parse("STEAM_1:0:84901")

        player = await steam.users.get_player_summary(steamid)
        if player is not None:
            print(player.personaname)

        friends = await steam.users.get_friends_list(steamid)
        print(f"{len(friends)} friends")

        games = await steam.library.get_owned_games(steamid)
        print(f"Owns {len(games)} games")


asyncio.run(main())
```

More examples:

```py
# No credential needed
async with Steam() as steam:
    count = await steam.stats.get_current_players(730)
    news = await steam.store.get_news_for_app(440, count=5)
    details = await steam.store.get_app_details(620)
    items = await steam.store.get_items([620, 440], include_assets=True)
    found = await steam.store.store_search("portal")
    wishlist = await steam.wishlist.get_wishlist("76561197960435530")
    price = await steam.market.get_item_price("AK-47 | Redline (Field-Tested)")
    inventory = await steam.economy.get_full_inventory("76561197960435530", 730)

# API key (or access token)
async with Steam(api_key="YOUR_API_KEY") as steam:
    level = await steam.users.get_steam_level("76561197960435530")
    recent = await steam.library.get_recently_played_games("76561197960435530")
    page = await steam.workshop.query_files(appid=440, numperpage=10)
    print([item.title for item in page.publishedfiledetails])

# Vanity name or profile URL to Steam ID
async with Steam(api_key="YOUR_API_KEY") as steam:
    steamid = await steam.users.resolve_vanity_url("robinwalker")

# The signed-in user's data needs their access token
async with Steam(access_token="YOUR_ACCESS_TOKEN") as steam:
    family = await steam.family.get_family_group_for_user()
    friends = await steam.friends.get_friends_list()
```

See the [`examples`](examples) directory for more.

### Namespaces

| Namespace | What it covers |
|---|---|
| `steam.users` | Profiles, friends lists, bans, vanity URLs, badges, Steam level |
| `steam.library` | Owned games, recently played games, last played times |
| `steam.stats` | Achievements, user and global stats, schemas, player counts |
| `steam.store` | App details, the app list, store items, search, news |
| `steam.wishlist` | Wishlists |
| `steam.workshop` | Workshop items |
| `steam.friends` | The signed-in user's friends |
| `steam.family` | Steam Families |
| `steam.notifications` | The signed-in user's notifications |
| `steam.servers` | Game servers |
| `steam.auth` | QR sign-in and access tokens |
| `steam.economy` | Community inventories |
| `steam.market` | The community market |
| `steam.util` | Server time, the list of supported API methods |

`steam.player` and `steam.games` from 1.x still work but raise
`DeprecationWarning`: use `steam.users`, and `steam.library` /
`steam.store` / `steam.stats`.

## Authorization

Each method sends only the credential it needs, and raises
`AuthenticationError` before making a request when that credential is
missing. `Steam()` itself needs none.

| Endpoints | Credential |
|---|---|
| Store (app details, store items, search), news, global stats, player counts, wishlists, `ISteamRemoteStorage` workshop details, `steam.util`, community market and inventory | none |
| `ISteamUser`, `ISteamUserStats` player methods (summaries, friends, bans, achievements, stats, schema) | API key |
| `IPlayerService` (owned and recently played games, badges, level), `IStoreService` (app list), `IPublishedFileService` (workshop details and queries) | API key, or the access token when there is no key |
| Steam Families, the signed-in user's friends list and last played times | access token |
| Market price history | `steamLoginSecure` cookie |

Credentials are passed to `Steam(...)` or read from the environment:

- **API key** (`api_key`, `STEAM_API_KEY`): get one at
  https://steamcommunity.com/dev/apikey
- **Access token** (`access_token`, `STEAM_ACCESS_TOKEN`): the token of a
  signed-in user.
  - Store token: open https://store.steampowered.com/pointssummary/ajaxgetasyncconfig
    and copy the value of `webapi_token`.
  - Community token: open https://steamcommunity.com/my/edit/info and run
    `JSON.parse(application_config.dataset.loyalty_webapi_token)` in the
    browser console.
- **Login cookie** (`steam_login_secure`, `STEAM_LOGIN_SECURE`): the value of
  the `steamLoginSecure` cookie of a signed-in steamcommunity.com session.
  Only `market.get_price_history()` uses it, and only steamcommunity.com
  receives it.

Treat all three like passwords. The library never logs them or puts them in
exception messages, and never sends the API key or token to
steamcommunity.com.

## Rate limits

By using the Steam Web API you agree to the
[Steam Web API Terms of Use](https://steamcommunity.com/dev/apiterms), which
limit each key to **100,000 calls per day**. Steam also rate limits by IP:
the store API allows roughly 200 requests per 5 minutes, and the community
market and inventory endpoints are much stricter and answer HTTP 429
quickly.

The client limits itself per Steam host, as a token bucket (a burst after an
idle period, then a steady rate):

| Host | Setting | Default |
|---|---|---|
| api.steampowered.com | `API_REQUESTS_PER_SECOND` / `API_BURST` | 1/s, burst 10 |
| store.steampowered.com | `STORE_REQUESTS_PER_SECOND` / `STORE_BURST` | 0.5/s, burst 10 |
| steamcommunity.com | `COMMUNITY_REQUESTS_PER_SECOND` / `COMMUNITY_BURST` | 0.25/s, burst 5 |

Set `API_KEY_DAILY_LIMIT` to stop before the daily quota runs out: once
that many requests with the key were sent in a UTC day, further ones raise
`RateLimitError` without being sent (`Client.api_key_requests_today` shows
the count).

```py
steam = Steam(api_key="...", api_requests_per_second=0.5, api_key_daily_limit=90_000)
```

Settings can also come from `STEAMY_`-prefixed environment variables, e.g.
`STEAMY_API_REQUESTS_PER_SECOND=0.5`. When Steam does rate limit a request
(HTTP 429), it is retried after `Retry-After` up to `MAX_RETRIES` times.

## Errors

Every exception derives from `SteamAPIError`:

- `AuthenticationError`: a credential is missing or rejected
- `RateLimitError`: rate limited (`retry_after` when known)
- `PrivateProfileError`, `PlayerNotFoundError`, `GameNotFoundError`
- `InvalidSteamIDError`, `InvalidAppIDError`: rejected before any request
- `ServiceUnavailableError`, `NetworkError`, `ResponseParsingError`

## Community market data

The market and inventory endpoints are unofficial steamcommunity.com pages,
not part of the Web API; Valve can change them at any time. For heavy market
or inventory use, third-party services such as
[steamwebapi.com](https://www.steamwebapi.com/) (commercial, not affiliated
with Valve) are an alternative.

## Thanks

- [xPaw](https://github.com/xPaw) for the
  [Steam Web API Documentation](https://steamapi.xpaw.me/), which this
  library leans on for endpoints, parameters and auth.
- [SteamDatabase/Protobufs](https://github.com/SteamDatabase/Protobufs) for
  the service response messages.
