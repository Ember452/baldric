"""CLI stream setup: keep stdout/stderr on UTF-8 where the console is not."""

from __future__ import annotations

import contextlib
import sys


def _is_utf8_encoding(encoding: str | None) -> bool:
    """Return whether a stream encoding name represents UTF-8."""
    if encoding is None:
        return False
    return encoding.lower().replace("-", "").replace("_", "") == "utf8"


def _force_utf8_streams() -> None:
    """Reconfigure stdout/stderr to UTF-8 when they are not already UTF-8.

    Windows consoles default these streams to the system codepage (e.g.
    cp1252), which raises UnicodeEncodeError on model output containing
    characters outside that codepage.
    """
    for stream in (sys.stdout, sys.stderr):
        if _is_utf8_encoding(getattr(stream, "encoding", None)):
            continue
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]


__all__ = ["_force_utf8_streams", "_is_utf8_encoding"]
