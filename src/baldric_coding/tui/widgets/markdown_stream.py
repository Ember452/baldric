"""Markdown stream coalescing for streamed transcript blocks.

Each Markdown append re-lays out every mounted transcript row, and providers
send 50-150 fragments/s, so appends are coalesced to ~10/s. Moved from
widgets/core.py to keep the transcript view wiring-only.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress

from textual.widgets import Markdown as TextualMarkdown

STREAM_FLUSH_INTERVAL_SECONDS = 0.1


class TranscriptMarkdownStream:
    """Like Textual's ``MarkdownStream``, but appends at most once per ``interval``.

    The first fragment is appended immediately.
    """

    def __init__(self, markdown: TextualMarkdown, *, interval: float) -> None:
        self._markdown = markdown
        self._interval = interval
        self._pending: list[str] = []
        self._wake = asyncio.Event()
        self._appending: asyncio.Future[None] | None = None
        self._task = asyncio.create_task(self._run())

    async def write(self, fragment: str) -> None:
        """Queue a fragment for the next flush."""
        if fragment:
            self._pending.append(fragment)
            self._wake.set()

    async def stop(self) -> None:
        """Stop the flush loop and append anything still queued."""
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        # Markdown.append reads its parse position before taking its lock, so an
        # append still in flight must finish before the final one starts.
        if self._appending is not None:
            await self._appending
        if self._pending:
            await self._markdown.append(self._take_pending())

    def _take_pending(self) -> str:
        text = "".join(self._pending)
        self._pending.clear()
        return text

    async def _run(self) -> None:
        while True:
            await self._wake.wait()
            self._wake.clear()
            self._appending = asyncio.ensure_future(self._markdown.append(self._take_pending()))
            await asyncio.shield(self._appending)
            await asyncio.sleep(self._interval)
