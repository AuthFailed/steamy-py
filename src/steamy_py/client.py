"""Async HTTP client with Steam API authentication and error handling."""

import asyncio
import logging
import re
import time
from collections.abc import Iterable, Mapping
from email.utils import parsedate_to_datetime
from typing import Any, NoReturn, cast
from urllib.parse import quote, quote_plus

import aiohttp
from aiohttp import ClientError, ClientResponse, ClientSession, ClientTimeout
from yarl import URL

from ._version import __version__
from .config import Settings
from .exceptions import (
    AuthenticationError,
    ConfigurationError,
    NetworkError,
    RateLimitError,
    ResponseParsingError,
    ServiceUnavailableError,
    SteamAPIError,
)

logger = logging.getLogger(__name__)

Params = Mapping[str, Any] | Iterable[tuple[str, Any]]

# Matches credential query parameters inside URLs embedded in error text.
_CREDENTIAL_PARAM_RE = re.compile(
    r"(?P<name>\b(?:key|access_token)=)[^&#\s'\"]+", re.IGNORECASE
)

_DEFAULT_HEADERS = {
    "User-Agent": f"steamy-py/{__version__}",
    "Accept": "application/json",
}

# Methods that can be repeated safely after a failure that may have reached
# Steam. Anything else (POST writes) is only retried when Steam provably did
# not process the request.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Steam EResult codes, sent in the ``x-eresult`` header by service methods.
_ERESULT_OK = 1
_ERESULT_AUTH = frozenset({5, 15, 21, 24})  # InvalidPassword, AccessDenied,
# NotLoggedOn, InsufficientPrivilege
_ERESULT_TRANSIENT = frozenset({10, 16, 20})  # Busy, Timeout, ServiceUnavailable
_ERESULT_RATE_LIMIT_EXCEEDED = 84

# HTTP statuses that mean "try again later" rather than "your request is wrong".
_UNAVAILABLE_STATUSES = frozenset({502, 503, 504})

# Which credential a request carries:
#   "none"          nothing
#   "api_key"       the Web API key (``key``)
#   "access_token"  the user's access token (``access_token``)
#   "any"           the API key if there is one, else the access token
#   "cookie"        the ``steamLoginSecure`` community login cookie
AUTH_TYPES = ("none", "api_key", "access_token", "any", "cookie")

_MISSING_CREDENTIAL = {
    "api_key": "API key is required but not provided",
    "access_token": "Access token is required but not provided",
    "cookie": "A steamLoginSecure cookie is required but not provided",
}

_SECONDS_PER_DAY = 86_400


class Client:
    """Async HTTP client with Steam API authentication."""

    def __init__(
        self,
        api_key: str | None = None,
        access_token: str | None = None,
        settings: Settings | None = None,
        session: ClientSession | None = None,
        steam_login_secure: str | None = None,
    ):
        """Initialize the client.

        Args:
            api_key: Steam API key for public endpoint authentication
            access_token: Steam access token for user-specific endpoint authentication
            settings: Optional settings configuration
            session: Optional aiohttp session to use. The client never closes a
                session it did not create.
            steam_login_secure: Value of the ``steamLoginSecure`` cookie of a
                signed-in steamcommunity.com session, for the few community
                endpoints that need a login (e.g. market price history)
        """
        self.api_key = api_key
        self.access_token = access_token
        self.steam_login_secure = steam_login_secure
        self.settings = settings or Settings()
        self._session: ClientSession | None = session
        self._owns_session = session is None
        self._limiters: dict[str, _RateLimiter] = {}
        self._api_key_day = -1
        self._api_key_requests = 0

    async def __aenter__(self):
        """Async context manager entry - creates session."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes session."""
        await self.close()

    async def connect(self):
        """Initialize aiohttp session."""
        if self._session is not None and not self._session.closed:
            return
        if not self._owns_session:
            raise ConfigurationError("The aiohttp session given to Client is closed")

        self._session = ClientSession(
            timeout=ClientTimeout(total=self.settings.REQUEST_TIMEOUT),
            connector=aiohttp.TCPConnector(limit=self.settings.CONNECTION_LIMIT),
            headers=_DEFAULT_HEADERS,
        )

        logger.debug("Steam API client connected")

    async def close(self):
        """Close the session (only if the client created it)."""
        if self._session is None or not self._owns_session:
            return
        if not self._session.closed:
            await self._session.close()
            logger.debug("Steam API client disconnected")
        self._session = None

    async def _rate_limit(self, url: str) -> None:
        """Wait for this request's slot on its host's rate limiter.

        Each Steam host (Web API, store, community) has its own limiter. A
        call reserves its slot before it waits, so concurrent requests are
        spaced out instead of being released together.
        """
        if not self.settings.RATE_LIMIT_ENABLED:
            return

        host = self._host_of(url)
        limiter = self._limiters.get(host)
        if limiter is None:
            rate, burst = self._host_limits(host)
            limiter = self._limiters[host] = _RateLimiter(rate, burst)
        delay = limiter.reserve(time.monotonic())
        if delay > 0:
            await asyncio.sleep(delay)

    def _host_of(self, url: str) -> str:
        """Which Steam host ("api", "store" or "community") ``url`` belongs to.

        The longest configured base URL that ``url`` starts with wins; a URL
        under none of them is matched by origin, else counts as "api".
        """
        bases = {
            "api": self.settings.STEAM_API_BASE_URL.rstrip("/"),
            "store": self.settings.STEAM_STORE_BASE_URL.rstrip("/"),
            "community": self.settings.STEAM_COMMUNITY_BASE_URL.rstrip("/"),
        }
        under = [
            (len(base), host)
            for host, base in bases.items()
            if url == base or url.startswith((base + "/", base + "?"))
        ]
        if under:
            return max(under)[1]
        origin = URL(url).origin()
        for host, base in bases.items():
            if URL(base).origin() == origin:
                return host
        return "api"

    def _host_limits(self, host: str) -> tuple[float, int]:
        """(requests per second, burst) configured for ``host``."""
        settings = self.settings
        if host == "store":
            return settings.STORE_REQUESTS_PER_SECOND, settings.STORE_BURST
        if host == "community":
            return settings.COMMUNITY_REQUESTS_PER_SECOND, settings.COMMUNITY_BURST
        return settings.API_REQUESTS_PER_SECOND, settings.API_BURST

    @property
    def api_key_requests_today(self) -> int:
        """Requests sent with the API key during the current UTC day."""
        if self._api_key_day != int(time.time() // _SECONDS_PER_DAY):
            return 0
        return self._api_key_requests

    def _spend_api_key_request(self) -> None:
        """Count a request carrying the API key against the daily limit.

        Raises:
            RateLimitError: If ``API_KEY_DAILY_LIMIT`` requests were already
                sent today (UTC); ``retry_after`` is the time to midnight
        """
        now = time.time()
        day = int(now // _SECONDS_PER_DAY)
        if day != self._api_key_day:
            self._api_key_day, self._api_key_requests = day, 0
        limit = self.settings.API_KEY_DAILY_LIMIT
        if limit is not None and self._api_key_requests >= limit:
            raise RateLimitError(
                f"Daily limit of {limit} API key requests reached "
                "(Settings.API_KEY_DAILY_LIMIT)",
                retry_after=(day + 1) * _SECONDS_PER_DAY - now,
                status_code=None,
            )
        self._api_key_requests += 1

    async def _get_session(self) -> ClientSession:
        """Return the open session, creating it if needed."""
        if self._session is None or self._session.closed:
            await self.connect()
        assert self._session is not None
        return self._session

    def _credential(self, auth_type: str) -> str | None:
        """The credential a request with ``auth_type`` carries, if any.

        Returns:
            "api_key", "access_token", "cookie", or None for "none"

        Raises:
            AuthenticationError: If the credential for ``auth_type`` is missing
            ValueError: If ``auth_type`` is not a known value
        """
        if auth_type == "none":
            return None
        if auth_type == "any":
            if not self.api_key and not self.access_token:
                raise AuthenticationError(
                    "An API key or access token is required but neither is provided",
                    status_code=None,
                )
            return "api_key" if self.api_key else "access_token"
        values = {
            "api_key": self.api_key,
            "access_token": self.access_token,
            "cookie": self.steam_login_secure,
        }
        if auth_type not in values:
            raise ValueError(
                f"Invalid auth_type: {auth_type}. "
                f"Must be one of {', '.join(AUTH_TYPES)}"
            )
        if not values[auth_type]:
            raise AuthenticationError(_MISSING_CREDENTIAL[auth_type], status_code=None)
        return auth_type

    def _apply_auth(
        self, params: Params | None, credential: str | None
    ) -> list[tuple[str, Any]]:
        """Return ``params`` as (key, value) pairs with the credential added.

        Repeated keys (from a MultiDict or a list of pairs) are kept. The
        caller's object is never modified. The cookie is sent as a header,
        not here.

        Raises:
            TypeError: If ``params`` is a string
        """
        pairs: list[tuple[str, Any]]
        if params is None:
            pairs = []
        elif isinstance(params, str | bytes):
            raise TypeError("params must be a mapping or (key, value) pairs")
        elif isinstance(params, Mapping):
            pairs = list(cast("Mapping[str, Any]", params).items())
        else:
            pairs = list(params)

        if credential == "api_key":
            name, value = "key", self.api_key
        elif credential == "access_token":
            name, value = "access_token", self.access_token
        else:
            return pairs
        return [pair for pair in pairs if pair[0] != name] + [(name, value)]

    def _request_options(
        self,
        method: str,
        pairs: list[tuple[str, Any]],
        credential: str | None,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        """Build the keyword arguments for ``ClientSession.request``."""
        options = dict(options)
        options["headers"] = {**_DEFAULT_HEADERS, **dict(options.get("headers") or {})}
        if credential == "cookie":
            options["headers"]["Cookie"] = f"steamLoginSecure={self.steam_login_secure}"
        if credential is not None:
            # A redirect target must never receive the credentials.
            options.setdefault("allow_redirects", False)
        if method == "POST" and "data" not in options and "json" not in options:
            # Steam service methods take POST inputs (and the credential) as a
            # form body, not in the query string.
            options["data"] = [(name, _form_value(value)) for name, value in pairs]
        else:
            options["params"] = pairs
        return options

    async def _send(
        self,
        session: ClientSession,
        method: str,
        url: str,
        credential_sent: bool,
        **options: Any,
    ) -> Any:
        """Send one request and return the parsed JSON body.

        Raises:
            _AttemptFailedError: Carrying the sanitized library exception and
                whether the request may be retried
        """
        try:
            async with session.request(method, url, **options) as response:
                return await self._read_response(response, method, credential_sent)
        except (aiohttp.ClientConnectorError, aiohttp.ConnectionTimeoutError) as e:
            # Nothing reached Steam, so any method may be retried.
            reason, retryable = self._describe_error(e), True
        except aiohttp.TooManyRedirects as e:
            url_without_query = e.request_info.real_url.with_query(None)
            reason = self._redact(f"Too many redirects for {url_without_query}")
            retryable = False
        except (ClientError, asyncio.TimeoutError) as e:
            reason = self._describe_error(e)
            retryable = method in _IDEMPOTENT_METHODS
        raise _AttemptFailedError(NetworkError(reason), retryable=retryable)

    async def _read_response(
        self, response: ClientResponse, method: str, credential_sent: bool
    ) -> Any:
        """Turn a response into its JSON body or an ``_AttemptFailedError``."""
        url = self._redact(str(response.request_info.real_url.with_query(None)))
        idempotent = method in _IDEMPOTENT_METHODS
        status = response.status

        if status == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            raise _AttemptFailedError(
                RateLimitError(
                    f"Rate limited by Steam (HTTP 429) for {url}",
                    retry_after=retry_after,
                ),
                retryable=True,
                retry_after=retry_after,
            )

        if not 200 <= status < 300:
            body = await self._read_body_safely(response)
            # A ``{"success": false}`` body is Steam's answer (e.g. an unknown
            # market item), not an outage, so it is not retried.
            raise _AttemptFailedError(
                self._http_error(response, url, credential_sent, body),
                retryable=status >= 500 and idempotent and not _is_unsuccessful(body),
            )

        eresult = _parse_eresult(response.headers.get("x-eresult"))
        if eresult is not None and eresult != _ERESULT_OK:
            body = await self._read_body_safely(response)
            error, retryable = self._eresult_error(response, url, eresult, body)
            # A rejected (rate limited) request was not processed, so even a
            # POST may be repeated; other transient failures only for GET.
            retryable = retryable and (idempotent or isinstance(error, RateLimitError))
            raise _AttemptFailedError(error, retryable=retryable)

        try:
            data = await response.json()
        except (ValueError, aiohttp.ContentTypeError) as e:
            reason = self._describe_error(e)
        else:
            logger.debug("Successful response from %s", url)
            return data

        raise _AttemptFailedError(
            ResponseParsingError(f"Invalid JSON response from {url}: {reason}"),
            retryable=False,
        )

    def _http_error(
        self, response: ClientResponse, url: str, credential_sent: bool, body: Any
    ) -> SteamAPIError:
        """The library exception for a non-2xx response."""
        status = response.status
        message = self._redact(
            " ".join(f"HTTP {status} {response.reason or ''} for {url}".split())
        )
        if status in (401, 403) and credential_sent:
            return AuthenticationError(message, status, body)
        if status in _UNAVAILABLE_STATUSES:
            return ServiceUnavailableError(message, status, body)
        return SteamAPIError(message, status, body)

    def _eresult_error(
        self, response: ClientResponse, url: str, eresult: int, body: Any
    ) -> tuple[SteamAPIError, bool]:
        """The library exception for a failing ``x-eresult``, and if retryable.

        ``retryable`` here means "Steam did not do the work"; the caller still
        limits retries of non-idempotent requests to rate limits.
        """
        status = response.status
        detail = response.headers.get("x-error_message") or "request failed"
        message = self._redact(f"Steam error EResult {eresult} ({detail}) for {url}")
        if eresult == _ERESULT_RATE_LIMIT_EXCEEDED:
            return RateLimitError(message, None, status, body, eresult), True
        if eresult in _ERESULT_AUTH:
            return AuthenticationError(message, status, body, eresult), False
        if eresult in _ERESULT_TRANSIENT:
            return ServiceUnavailableError(message, status, body, eresult), True
        return SteamAPIError(message, status, body, eresult), False

    async def _read_body_safely(self, response: ClientResponse) -> Any:
        """Return an error response's body (JSON if possible), or None."""
        try:
            text = await response.text()
        except Exception:
            return None
        try:
            return await response.json(content_type=None)
        except ValueError:
            return self._redact(text[:2000]) if text else None

    async def request(
        self,
        method: str,
        url: str,
        params: Params | None = None,
        auth_type: str = "api_key",
        **kwargs,
    ) -> Any:
        """Make authenticated request to Steam API.

        GET requests send ``params`` in the query string; POST requests send
        them, with the credential, as a form body. Requests carrying a
        credential never follow redirects.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Complete URL to request
            params: Request parameters, as a mapping or (key, value) pairs
            auth_type: Credential to send: "none", "api_key", "access_token",
                "any" (the API key if set, else the access token) or "cookie"
                (the ``steamLoginSecure`` cookie)
            **kwargs: Additional aiohttp parameters

        Returns:
            JSON response data

        Raises:
            AuthenticationError: If the credential is missing, rejected
                (HTTP 401/403) or lacks access (EResult AccessDenied etc.)
            RateLimitError: If Steam rate limited the request (HTTP 429 or
                EResult RateLimitExceeded), or ``API_KEY_DAILY_LIMIT`` is used
                up; ``retry_after`` is set when known
            ServiceUnavailableError: On HTTP 502/503/504 or a busy Steam
            NetworkError: On connection errors and timeouts
            ResponseParsingError: On invalid JSON response
            SteamAPIError: On any other HTTP error or failing ``x-eresult``
                (``status_code``, ``eresult`` and ``response_data`` are set)
            ValueError: If ``auth_type`` is invalid
            TypeError: If ``params`` is a string

        Server errors, timeouts and rate limits are retried up to
        ``MAX_RETRIES`` times; client errors (4xx) never are, and POST
        requests are only retried when Steam provably did not process them.
        When attempts fail in different ways, the last error that was not a
        rate limit is raised. Error messages and logs never contain the API
        key or access token.
        """
        method = method.upper()
        credential = self._credential(auth_type)
        pairs = self._apply_auth(params, credential)
        options = self._request_options(method, pairs, credential, kwargs)
        session = await self._get_session()

        # Only sanitized library exceptions leave this method, and never with
        # the original aiohttp error (which embeds the full URL with
        # credentials) attached as __cause__ or __context__.
        failure: SteamAPIError | None = None
        attempts = self.settings.MAX_RETRIES + 1
        for attempt in range(attempts):
            if credential == "api_key":
                self._spend_api_key_request()
            await self._rate_limit(url)
            logger.debug(
                "Making %s request to %s (attempt %d)",
                method,
                self._redact(url),
                attempt + 1,
            )
            try:
                return await self._send(
                    session, method, url, credential is not None, **options
                )
            except _AttemptFailedError as e:
                outcome = e

            error = outcome.error
            # Report the last real failure; a rate limit only when nothing else
            # went wrong.
            if not isinstance(error, RateLimitError) or (
                failure is None or isinstance(failure, RateLimitError)
            ):
                failure = error

            delay = outcome.retry_after
            if delay is None:
                delay = self.settings.RETRY_DELAY * (2**attempt)
            if (
                not outcome.retryable
                or attempt == attempts - 1
                or delay > self.settings.MAX_RETRY_WAIT
            ):
                break

            logger.warning(
                "Request failed (attempt %d), retrying in %s seconds: %s",
                attempt + 1,
                delay,
                error,
            )
            await asyncio.sleep(delay)

        logger.error("Request failed after %d attempt(s): %s", attempt + 1, failure)
        _raise_unchained(failure or SteamAPIError("Request failed for unknown reason"))

    def _redact(self, text: str) -> str:
        """Remove the API key, access token and login cookie from ``text``."""
        for secret in (self.api_key, self.access_token, self.steam_login_secure):
            if secret:
                for form in _encoded_forms(secret):
                    text = text.replace(form, "***")
        return _CREDENTIAL_PARAM_RE.sub(r"\g<name>***", text)

    def _describe_error(self, error: BaseException) -> str:
        """Describe an aiohttp error without leaking credentials."""
        if isinstance(error, aiohttp.ClientResponseError):
            url = error.request_info.real_url.with_query(None)
            return self._redact(f"HTTP {error.status} {error.message} for {url}")
        if isinstance(error, asyncio.TimeoutError) and not str(error):
            return "TimeoutError: the request timed out"
        return self._redact(f"{type(error).__name__}: {error}")


class _RateLimiter:
    """A token bucket (as GCRA): ``burst`` requests at once, then ``rate``/s.

    ``reserve`` books the next slot and returns how long to wait for it, so
    concurrent callers queue up in order.
    """

    def __init__(self, rate: float, burst: int) -> None:
        self._interval = 1.0 / rate
        self._tolerance = (burst - 1) * self._interval
        self._theoretical_arrival = 0.0

    def reserve(self, now: float) -> float:
        """Book a slot; return the seconds to wait before using it."""
        arrival = max(self._theoretical_arrival, now)
        self._theoretical_arrival = arrival + self._interval
        return max(0.0, arrival - self._tolerance - now)


class _AttemptFailedError(Exception):
    """Internal: one attempt failed with ``error``; it may be retried."""

    def __init__(
        self,
        error: SteamAPIError,
        retryable: bool,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(str(error))
        self.error = error
        self.retryable = retryable
        self.retry_after = retry_after


def _is_unsuccessful(body: Any) -> bool:
    """Whether ``body`` is Steam's ``{"success": false}`` reply."""
    return isinstance(body, dict) and body.get("success") in (False, 0)


def _form_value(value: Any) -> str:
    """Encode a form value; booleans become "1"/"0" like Steam expects."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)


def _parse_eresult(value: str | None) -> int | None:
    """Parse the ``x-eresult`` header, ignoring garbage."""
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def _parse_retry_after(value: str | None) -> float | None:
    """Parse ``Retry-After`` as seconds or an HTTP date; None if absent/invalid."""
    if value is None:
        return None
    value = value.strip()
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    return max(0.0, when.timestamp() - time.time())


def _encoded_forms(secret: str) -> set[str]:
    """The ways ``secret`` can appear in a URL or in error text."""
    yarl_form = URL.build(query={"x": secret}).raw_query_string.removeprefix("x=")
    return {secret, quote(secret, safe=""), quote_plus(secret), yarl_form}


def _raise_unchained(error: Exception) -> NoReturn:
    """Raise ``error`` with no exception attached as its context.

    Raising outside an ``except`` block is not enough: under the pure-Python
    asyncio Task a coroutine resumed with an exception (e.g. a refused
    connection) still sees that exception as "being handled", and Python would
    attach it as ``__context__``.
    """
    try:
        raise error
    finally:
        error.__context__ = None
