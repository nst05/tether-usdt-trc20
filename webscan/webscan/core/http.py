"""Async HTTP client used by every plugin.

Built on :mod:`aiohttp`. A single :class:`HttpClient` is shared by the whole
scan so that connection pooling, the global concurrency limit, jitter and
optional proxying are applied uniformly. This is what lets the scanner open
thousands of in-flight requests on a single event loop instead of paying for a
thread per connection.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any

import aiohttp

# A small pool of common, real-looking desktop User-Agents. Rotation in stealth
# mode is about spreading load across plausible clients, not impersonation.
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
]

DEFAULT_USER_AGENT = "WebScan/0.1 (+https://example.invalid/webscan; authorized-testing-only)"


@dataclass
class Response:
    """A lightweight, fully-buffered view of an HTTP response."""

    url: str
    status: int
    headers: dict[str, str]
    text: str
    elapsed: float
    history: list[int] = field(default_factory=list)

    def header(self, name: str, default: str = "") -> str:
        # aiohttp headers are case-insensitive; we copy into a plain dict so
        # we re-implement a case-insensitive lookup here.
        lname = name.lower()
        for key, value in self.headers.items():
            if key.lower() == lname:
                return value
        return default


@dataclass
class RequestStats:
    sent: int = 0
    failed: int = 0
    bytes_in: int = 0


class HttpClient:
    def __init__(
        self,
        *,
        concurrency: int = 20,
        timeout: float = 15.0,
        jitter: tuple[float, float] = (0.0, 0.0),
        rotate_user_agent: bool = False,
        proxy: str | None = None,
        retries: int = 1,
        verify_ssl: bool = True,
        max_body_bytes: int = 2_000_000,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._jitter = jitter
        self._rotate_ua = rotate_user_agent
        self._proxy = proxy
        self._retries = max(1, retries)
        self._verify_ssl = verify_ssl
        self._max_body = max_body_bytes
        self._extra_headers = extra_headers or {}
        self._session: aiohttp.ClientSession | None = None
        self.stats = RequestStats()

    async def __aenter__(self) -> "HttpClient":
        connector = aiohttp.TCPConnector(ssl=self._verify_ssl, limit=0)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=self._timeout,
            trust_env=True,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None

    def _build_headers(self, override: dict[str, str] | None) -> dict[str, str]:
        headers = {
            "User-Agent": random.choice(USER_AGENTS) if self._rotate_ua else DEFAULT_USER_AGENT,
            "Accept": "*/*",
        }
        headers.update(self._extra_headers)
        if override:
            headers.update(override)
        return headers

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        params: dict[str, str] | None = None,
        data: Any = None,
        allow_redirects: bool = True,
    ) -> Response | None:
        """Perform a request, returning ``None`` on unrecoverable failure."""
        if self._session is None:
            raise RuntimeError("HttpClient must be used as an async context manager")

        last_exc: Exception | None = None
        for attempt in range(self._retries):
            lo, hi = self._jitter
            if hi > 0:
                await asyncio.sleep(random.uniform(lo, hi))
            async with self._sem:
                start = time.monotonic()
                try:
                    async with self._session.request(
                        method.upper(),
                        url,
                        headers=self._build_headers(headers),
                        params=params,
                        data=data,
                        proxy=self._proxy,
                        allow_redirects=allow_redirects,
                    ) as resp:
                        raw = await resp.content.read(self._max_body)
                        text = raw.decode(resp.charset or "utf-8", "replace")
                        self.stats.sent += 1
                        self.stats.bytes_in += len(raw)
                        return Response(
                            url=str(resp.url),
                            status=resp.status,
                            headers={k: v for k, v in resp.headers.items()},
                            text=text,
                            elapsed=time.monotonic() - start,
                            history=[h.status for h in resp.history],
                        )
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_exc = exc
                    if attempt + 1 < self._retries:
                        await asyncio.sleep(0.5 * (attempt + 1))
                        continue
        self.stats.failed += 1
        return None

    async def get(self, url: str, **kwargs: Any) -> Response | None:
        return await self.request("GET", url, **kwargs)

    async def head(self, url: str, **kwargs: Any) -> Response | None:
        return await self.request("HEAD", url, **kwargs)
