"""Tolerant JSON parsing shared by the provider stream adapters.

Provider adapters each receive JSON fragments off an SSE connection and must
skip malformed ones without aborting the stream. Every adapter had its own
near-identical ``_loads_object`` helper (six copies that had already drifted in
variable names and return types); keep the single implementation here so a fix
in one place covers them all.

``parse_sse_data_line`` is deliberately *not* provided: adapters disagree on
whether ``[DONE]`` is the parser's concern or the stream loop's, and unifying
them changed behaviour. Only the genuinely identical helper lives here.
"""

from __future__ import annotations

from json import loads
from typing import Any

__all__ = ["loads_object"]


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
