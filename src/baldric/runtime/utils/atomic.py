"""Crash-safe file writes for user-visible artifacts."""

from __future__ import annotations

import os
import tempfile
from contextlib import suppress
from pathlib import Path


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    """Replace ``path`` with ``text`` without ever leaving a partial file.

    A plain ``write_text`` truncates first, so an interrupted write destroys the
    previous file. Writing a same-directory temporary file, fsyncing it, and
    replacing the target keeps the old content until the new content is durable.

    The directory entry is not fsynced: on a crash right after the replace the
    previous file may reappear, which is a reverted update rather than a partial
    one. Transcript storage already pays for directory fsync where batch writes
    need it.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(descriptor, "wb") as file:
            file.write(text.encode(encoding))
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        with suppress(OSError):
            os.unlink(temporary)
        raise
