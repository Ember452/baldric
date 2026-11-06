"""HTTP client helpers shared by Baldric network integrations."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager, suppress
from typing import Any

import httpx

from baldric_agent.provider import CancellationToken

_PROXY_ENV_VARS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def normalize_proxy_url(proxy_url: str) -> str:
    """Return an httpx-compatible proxy URL.

    Some environments use ``socks://`` as a generic SOCKS proxy scheme. httpx
    accepts explicit SOCKS versions (for example ``socks5://`` and
    ``socks5h://``), but rejects the generic scheme before it can make a
    request. Treat the generic form as SOCKS5 so Baldric can honor these proxy
    environment variables.
    """

    if proxy_url.lower().startswith("socks://"):
        return f"socks5://{proxy_url[len('socks://') :]}"
    return proxy_url


@contextmanager
def normalized_proxy_environment() -> Iterator[None]:
    """Temporarily normalize proxy environment variables for httpx construction."""

    original: dict[str, str | None] = {}
    changed = False
    for name in _PROXY_ENV_VARS:
        value = os.environ.get(name)
        if value is None:
            continue
        normalized = normalize_proxy_url(value)
        if normalized == value:
            continue
        original[name] = value
        os.environ[name] = normalized
        changed = True

    try:
        yield
    finally:
        if changed:
            for name, value in original.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value


def create_async_client(**kwargs: Any) -> httpx.AsyncClient:
    """Create an ``httpx.AsyncClient`` with Baldric's proxy normalization applied."""

    with normalized_proxy_environment():
        return httpx.AsyncClient(**kwargs)


async def iter_sse_lines(
    response: httpx.Response,
    signal: CancellationToken | None,
) -> AsyncIterator[str]:
    """Yield response lines, stopping as soon as the run is cancelled.

    Checking the token between lines is not enough: while a provider holds the
    connection open (a queued request, a stalled upstream) no line arrives, so a
    cancel would wait for the full read timeout. Racing each read against
    ``wait_cancelled`` keeps cancellation prompt; the caller still has to stop
    finalizing once this iterator ends early.
    """

    if signal is None:
        async for line in response.aiter_lines():
            yield line
        return

    lines = response.aiter_lines().__aiter__()
    while True:
        if signal.is_cancelled():
            return
        next_line = asyncio.ensure_future(anext(lines))
        # One waiter per read, cancelled as soon as the read wins: a waiter that
        # outlived the yield would stay pending for every request that ends
        # normally, because a caller leaving the loop does not close this
        # generator.
        cancelled = asyncio.ensure_future(signal.wait_cancelled())
        done, _pending = await asyncio.wait(
            {next_line, cancelled},
            return_when=asyncio.FIRST_COMPLETED,
        )
        cancelled.cancel()
        with suppress(asyncio.CancelledError):
            await cancelled
        if next_line not in done:
            next_line.cancel()
            with suppress(asyncio.CancelledError):
                await next_line
            return
        try:
            line = next_line.result()
        except StopAsyncIteration:
            return
        yield line


def get_json(url: str, *, timeout: float, follow_redirects: bool = False) -> dict[str, object]:
    """Fetch a JSON object with Baldric's proxy normalization applied."""

    with normalized_proxy_environment():
        response = httpx.get(url, timeout=timeout, follow_redirects=follow_redirects)
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("HTTP response must be a JSON object")
    return data
