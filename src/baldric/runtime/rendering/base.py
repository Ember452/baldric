"""Shared event-rendering primitives for Baldric coding modes."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol

from baldric.runtime.events import CodingSessionEvent


class PrintOutputMode(StrEnum):
    """Output modes supported by non-interactive print mode."""

    text = "text"
    json = "json"
    transcript = "transcript"
    rpc = "rpc"


FAILED_STOP_REASONS: frozenset[str] = frozenset({"error", "aborted", "length"})
"""Stop reasons that must make a headless run exit non-zero.

`length` belongs here because a response cut off at the output-token limit did
not finish the job the caller asked for. Pi treats it the same way. Every print
renderer used to decide this on its own - one failed only on `error`, another
reset the flag on `aborted` - so the same event stream produced different exit
codes depending on the output mode.
"""


def is_failed_stop_reason(stop_reason: str | None) -> bool:
    """Return whether a terminal assistant stop reason fails the run."""
    return stop_reason in FAILED_STOP_REASONS


class EventRenderer(Protocol):
    """Consumes agent events and renders them for a frontend or output mode."""

    def render(self, event: CodingSessionEvent) -> None:
        """Render one event."""

    def finish(self) -> bool:
        """Finish rendering and return whether the run succeeded."""
