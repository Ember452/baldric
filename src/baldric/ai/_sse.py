"""Tolerant JSON and SSE framing helpers shared by the provider stream adapters.

Provider adapters each receive text fragments off an SSE connection and must
skip malformed ones without aborting the stream. Every adapter had its own
near-identical ``_loads_object`` helper (six copies that had already drifted in
variable names and return types); keep the single implementation here so a fix
in one place covers them all.

``iter_sse_events`` is the single SSE framing parser. Four adapters had reduced
it to "one ``data:`` line per event", which silently drops any event a proxy or
gateway split across several ``data:`` lines. It deliberately does not interpret
``[DONE]``: the sentinel is data, and each provider decides whether it ends the
stream, is ignored, or is malformed.
"""

from __future__ import annotations

from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from json import loads
from typing import Any

__all__ = ["SSEEvent", "iter_sse_events", "loads_object"]


@dataclass(frozen=True, slots=True)
class SSEEvent:
    """One dispatched server-sent event."""

    data: str
    event: str | None = None


async def iter_sse_events(lines: AsyncIterable[str]) -> AsyncIterator[SSEEvent]:
    """Parse an SSE line stream into dispatched events.

    Handles the framing every adapter needs: multi-line ``data:`` values are
    joined with ``\\n`` per the SSE specification, an ``event:`` field names the
    event, a blank line dispatches it, comment lines (``:``) are ignored, and a
    trailing event without a final blank line is still dispatched at EOF.
    Line endings are already split by the caller (``iter_sse_lines`` handles
    CRLF/CR/LF), but a stray trailing ``\\r`` is tolerated too. Empty data
    payloads dispatch nothing, matching the previous per-line adapters.
    """
    data_lines: list[str] = []
    event_name: str | None = None
    async for raw_line in lines:
        line = raw_line.rstrip("\r").strip()
        if not line:
            if data_lines:
                data = "\n".join(data_lines).strip()
                data_lines = []
                name = event_name
                event_name = None
                if data:
                    yield SSEEvent(data=data, event=name)
            else:
                event_name = None
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if not separator:
            continue
        if field == "data":
            data_lines.append(value[1:] if value.startswith(" ") else value)
        elif field == "event":
            event_name = value[1:] if value.startswith(" ") else value

    if data_lines:
        data = "\n".join(data_lines).strip()
        if data:
            yield SSEEvent(data=data, event=event_name)


def loads_object(text: str) -> dict[str, Any] | None:
    """Parse ``text`` as a JSON object, returning ``None`` if it is not one.

    ``json.loads`` only raises :class:`json.JSONDecodeError` (a ``ValueError``)
    for malformed input, so catching ``ValueError`` covers every adapter's
    previous behaviour (some caught the narrower ``JSONDecodeError``).
    """
    try:
        value = loads(text)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None
