"""A local HTTP server that stands in for Steam during tests.

One server plays all three Steam hosts; the client is pointed at it through
``Settings``:

- ``/``           -> api.steampowered.com      (STEAM_API_BASE_URL)
- ``/store-api``  -> store.steampowered.com/api (STEAM_STORE_BASE_URL)
- ``/community``  -> steamcommunity.com         (STEAM_COMMUNITY_BASE_URL)
"""

from __future__ import annotations

import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.test_utils import TestServer
from multidict import MultiDict

FIXTURES_DIR = Path(__file__).parent / "fixtures"

API_KEY = "TESTAPIKEY0123456789ABCDEF"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJFZERTQSJ9.test-access-token_value"
STEAMID = "76561197960435530"
STORE_PREFIX = "/store-api"
COMMUNITY_PREFIX = "/community"


def load_fixture(name: str) -> Any:
    """Load ``tests/fixtures/<name>`` as JSON."""
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


@dataclass
class RecordedRequest:
    """A request received by the fake server."""

    method: str
    path: str
    query: MultiDict[str]
    form: MultiDict[str]
    headers: dict[str, str]
    body: bytes

    @property
    def params(self) -> dict[str, str]:
        """Query parameters as a plain dict (last value wins)."""
        return dict(self.query)


@dataclass
class _Reply:
    status: int = 200
    json: Any = None
    text: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    content_type: str | None = None


class FakeSteam:
    """Queue canned replies per (method, path) and record every request.

    Replies registered for the same route are served in order; the last one is
    repeated for any further requests. Unregistered routes answer 404.
    """

    def __init__(self) -> None:
        self._replies: dict[tuple[str, str], deque[_Reply]] = defaultdict(deque)
        self.requests: list[RecordedRequest] = []
        self._server: TestServer | None = None

    # -- server lifecycle -------------------------------------------------

    async def start(self) -> None:
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self._handle)
        self._server = TestServer(app)
        await self._server.start_server()

    async def close(self) -> None:
        if self._server is not None:
            await self._server.close()

    @property
    def url(self) -> str:
        """Base URL of the server, without a trailing slash."""
        assert self._server is not None, "server not started"
        return str(self._server.make_url("")).rstrip("/")

    # -- configuring replies ----------------------------------------------

    def add(
        self,
        method: str,
        path: str,
        *,
        json: Any = None,
        status: int = 200,
        text: str | None = None,
        headers: dict[str, str] | None = None,
        content_type: str | None = None,
    ) -> None:
        """Register a reply for ``method`` + ``path`` (path without query).

        Pass ``json`` for a JSON body, or ``text`` (+ ``content_type``) for a
        raw body. ``json=None`` with no ``text`` sends an empty body.
        """
        self._replies[(method.upper(), path)].append(
            _Reply(
                status=status,
                json=json,
                text=text,
                headers=headers or {},
                content_type=content_type,
            )
        )

    def api(self, method: str, path: str, **kwargs: Any) -> None:
        """Register a reply on the Web API host (api.steampowered.com)."""
        self.add(method, path, **kwargs)

    def store(self, method: str, path: str, **kwargs: Any) -> None:
        """Register a reply on the store host (``path`` relative to /api)."""
        self.add(method, STORE_PREFIX + path, **kwargs)

    def community(self, method: str, path: str, **kwargs: Any) -> None:
        """Register a reply on the community host (steamcommunity.com)."""
        self.add(method, COMMUNITY_PREFIX + path, **kwargs)

    # -- inspecting requests ----------------------------------------------

    def requests_to(self, path: str) -> list[RecordedRequest]:
        """All recorded requests for an exact path."""
        return [r for r in self.requests if r.path == path]

    @property
    def last(self) -> RecordedRequest:
        """The most recent request."""
        assert self.requests, "no requests were made"
        return self.requests[-1]

    # -- handler ----------------------------------------------------------

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        body = await request.read()
        form: MultiDict[str] = MultiDict()
        if request.content_type == "application/x-www-form-urlencoded":
            form = MultiDict(await request.post())  # type: ignore[arg-type]
        self.requests.append(
            RecordedRequest(
                method=request.method,
                path=request.path,
                query=MultiDict(request.query),
                form=form,
                headers=dict(request.headers),
                body=body,
            )
        )

        queue = self._replies.get((request.method, request.path))
        if not queue:
            return web.json_response(
                {"error": f"no fake reply for {request.method} {request.path}"},
                status=404,
            )
        reply = queue.popleft() if len(queue) > 1 else queue[0]

        if reply.text is not None:
            return web.Response(
                status=reply.status,
                text=reply.text,
                headers=reply.headers,
                content_type=reply.content_type or "text/plain",
            )
        if reply.json is None:
            return web.Response(status=reply.status, headers=reply.headers)
        return web.json_response(reply.json, status=reply.status, headers=reply.headers)
