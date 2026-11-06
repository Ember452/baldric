"""Cancellation must interrupt a read that never produces data.

Polling the token between SSE lines only helps when a line eventually arrives.
These tests cover the stalled case: the server accepts the request and then says
nothing, which used to block until the read timeout.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator

import pytest

from baldric_agent import SimpleCancellationToken
from baldric_ai.http import iter_sse_lines


class _StalledResponse:
    """A response whose line iterator never yields."""

    def __init__(self, lines: list[str] | None = None) -> None:
        self._lines = lines or []
        self.reads = 0

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            self.reads += 1
            yield line
        if self._lines:
            return
        self.reads += 1
        await asyncio.sleep(3600)


class _IdleResponse:
    """A response that yields nothing and returns immediately."""

    async def aiter_lines(self) -> AsyncIterator[str]:
        return
        yield ""  # pragma: no cover - unreachable, keeps this an async generator


async def _cancel_after(signal: SimpleCancellationToken, delay: float) -> None:
    await asyncio.sleep(delay)
    signal.cancel()


@pytest.mark.anyio
async def test_cancellation_interrupts_a_stalled_read() -> None:
    response = _StalledResponse()
    signal = SimpleCancellationToken()
    canceller = asyncio.create_task(_cancel_after(signal, 0.05))

    started = time.monotonic()
    lines = [line async for line in iter_sse_lines(response, signal)]  # type: ignore[arg-type]
    elapsed = time.monotonic() - started
    await canceller

    assert lines == []
    assert elapsed < 1.0, f"cancellation took {elapsed:.2f}s"
    assert response.reads == 1


@pytest.mark.anyio
async def test_already_cancelled_token_reads_nothing() -> None:
    response = _StalledResponse()
    signal = SimpleCancellationToken()
    signal.cancel()

    lines = [line async for line in iter_sse_lines(response, signal)]  # type: ignore[arg-type]

    assert lines == []
    assert response.reads == 0


@pytest.mark.anyio
async def test_lines_pass_through_without_a_token() -> None:
    response = _StalledResponse(lines=["data: one", "data: two"])

    lines = [line async for line in iter_sse_lines(response, None)]  # type: ignore[arg-type]

    assert lines == ["data: one", "data: two"]


@pytest.mark.anyio
async def test_idle_stream_ends_normally() -> None:
    signal = SimpleCancellationToken()

    lines = [line async for line in iter_sse_lines(_IdleResponse(), signal)]  # type: ignore[arg-type]

    assert lines == []
