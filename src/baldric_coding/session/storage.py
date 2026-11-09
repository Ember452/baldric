"""Locked, append-only session storage implementations."""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol

from baldric_protocol.session.entries import SessionEntry
from baldric_protocol.session.jsonl import (
    SessionJsonlError,
    entries_from_transcript,
    entry_from_json_line,
    entry_to_json_line,
)

logger = logging.getLogger(__name__)

_BRANCHABLE_ENTRY_TYPES = frozenset({"message", "compaction", "branch_summary"})


class SessionStorage(Protocol):
    """Append-only session storage interface.

    ``append_batch`` is the durable transaction boundary used by startup,
    replacement, and model selection. Implementations must make the complete
    batch visible or leave the previous transcript untouched.
    """

    async def append(self, entry: SessionEntry) -> None:
        """Append one entry to storage."""
        ...

    async def append_batch(self, entries: Sequence[SessionEntry]) -> None:
        """Atomically append a complete batch of entries."""
        ...

    async def read_all(self) -> list[SessionEntry]:
        """Read all entries in storage order."""
        ...


@dataclass(frozen=True, slots=True)
class _ParsedTranscript:
    """Entries parsed from a transcript file plus the file stamp they match."""

    stamp: tuple[int, int, int]
    entries: tuple[SessionEntry, ...]


class JsonlSessionStorage:
    """Local JSONL storage with a per-session cross-process lock.

    The lock is deliberately separate from the transcript. Readers use a
    shared lock when the platform provides one; every write uses an exclusive
    lock and re-reads the current file before changing it. Batch writes use a
    same-directory temporary file, fsync, replace, and directory fsync.

    Parsed entries are kept between reads. Sessions persist after every
    message and then read the transcript back, and parsing a long transcript
    takes far longer than appending to it. A read reuses the parsed entries
    while the file's (mtime, size, inode) stamp is unchanged, and this
    storage's own appends extend them in place; any other change to the file
    triggers a full re-read.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(f".{self.path.name}.lock")
        self.temp_path = self.path.with_name(f".{self.path.name}.tmp")
        self._parsed: _ParsedTranscript | None = None

    async def append(self, entry: SessionEntry) -> None:
        """Append one entry under the session's exclusive cross-process lock."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._append_locked(entry_to_json_line(entry))

    def append_sync(self, entry: SessionEntry) -> None:
        """Append one entry synchronously under the same exclusive lock.

        Slash commands that cannot await storage need a synchronous append;
        without it they would bypass the cross-process lock, the torn-tail
        repair, and the fsync that :meth:`append` provides.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._append_locked(entry_to_json_line(entry))

    def _append_locked(self, line: str) -> None:
        """Write one encoded line under the already-held exclusive lock."""
        with self._locked(exclusive=True):
            self._remove_incomplete_temp()
            self._repair_torn_tail()
            previous_stamp = self._file_stamp()
            try:
                with self.path.open("ab") as file:
                    file.write(line.encode("utf-8"))
                    file.flush()
                    os.fsync(file.fileno())
            except BaseException:
                self._parsed = None
                raise
            self._extend_parsed(previous_stamp, (line,))

    async def append_batch(self, entries: Sequence[SessionEntry]) -> None:
        """Atomically append all entries, preserving the old file on failure."""
        batch = tuple(entries)
        if not batch:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lines = tuple(entry_to_json_line(entry) for entry in batch)
        encoded = "".join(lines).encode("utf-8")
        with self._locked(exclusive=True):
            self._remove_incomplete_temp()
            previous_stamp = self._file_stamp()
            previous = self.path.read_bytes() if previous_stamp is not None else b""
            previous, repaired = _repair_tail_bytes(previous)
            if repaired:
                self._parsed = None
                logger.warning("Repaired a partial final line before appending to %s", self.path)
            data = previous + encoded
            try:
                self._atomic_replace(data)
            except BaseException:
                self._parsed = None
                raise
            self._extend_parsed(previous_stamp, lines)

    async def read_all(self) -> list[SessionEntry]:
        """Read all entries in file order; missing files are empty sessions."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # A fixed temp name makes crash recovery deterministic. If it exists,
        # take an exclusive lock and discard it; it was never the commit file.
        if self.temp_path.exists():
            with self._locked(exclusive=True):
                self._remove_incomplete_temp()
                return self._read_unlocked()
        with self._locked(exclusive=False):
            return self._read_unlocked()

    def _read_unlocked(self) -> list[SessionEntry]:
        stamp = self._file_stamp()
        if stamp is None:
            self._parsed = None
            return []
        parsed = self._parsed
        if parsed is not None and parsed.stamp == stamp:
            return _isolated_entries(parsed.entries)
        entries, dropped_tail = entries_from_transcript(self.path.read_text(encoding="utf-8"))
        if dropped_tail:
            logger.warning("Dropped a partial final line while reading %s", self.path)
        self._parsed = _ParsedTranscript(stamp=stamp, entries=tuple(entries))
        return _isolated_entries(entries)

    def _extend_parsed(self, previous_stamp: tuple[int, int, int] | None, lines: Sequence[str]) -> None:
        """Record lines this storage just appended, if the cache saw the file before."""
        parsed = self._parsed
        previous: tuple[SessionEntry, ...]
        if previous_stamp is None:
            previous = ()
        elif parsed is not None and parsed.stamp == previous_stamp:
            previous = parsed.entries
        else:
            self._parsed = None
            return
        if not _appending_preserves_legacy_labels(previous):
            self._parsed = None
            return
        stamp = self._file_stamp()
        if stamp is None:
            self._parsed = None
            return
        # Parse the written lines back instead of caching the caller's objects,
        # so cached reads match a full re-read and never alias live models.
        appended = tuple(entry_from_json_line(line) for line in lines)
        self._parsed = _ParsedTranscript(stamp=stamp, entries=(*previous, *appended))

    def _file_stamp(self) -> tuple[int, int, int] | None:
        try:
            stat = self.path.stat()
        except FileNotFoundError:
            return None
        return (stat.st_mtime_ns, stat.st_size, stat.st_ino)

    def _atomic_replace(self, data: bytes) -> None:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        # Keep the stable recovery marker in addition to the unique temp. A
        # crash between writes leaves a safely removable artifact.
        try:
            os.close(descriptor)
            temporary_path = Path(temporary)
            with temporary_path.open("wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary_path, self.path)
            _fsync_directory(self.path.parent)
        except BaseException:
            with _suppress_os_error():
                Path(temporary).unlink()
            raise

    def _remove_incomplete_temp(self) -> None:
        with _suppress_os_error():
            self.temp_path.unlink()
        # Also clean unique temp files left by a process killed during a
        # replacement. They are never authoritative because replace is atomic.
        prefix = f".{self.path.name}."
        for candidate in self.path.parent.glob(f"{prefix}*.tmp"):
            with _suppress_os_error():
                candidate.unlink()

    def _repair_torn_tail(self) -> None:
        """Terminate or drop a partial final line before appending.

        Appending onto an unterminated line would glue the new record onto the
        old fragment, turning one damaged line into a damaged transcript.
        """
        if self._ends_with_newline():
            return
        repaired, changed = _repair_tail_bytes(self.path.read_bytes())
        if not changed:
            return
        self._atomic_replace(repaired)
        self._parsed = None
        logger.warning("Repaired a partial final line before appending to %s", self.path)

    def _ends_with_newline(self) -> bool:
        try:
            with self.path.open(mode="rb") as file:
                file.seek(0, os.SEEK_END)
                if file.tell() == 0:
                    return True
                file.seek(-1, os.SEEK_END)
                return file.read(1) == b"\n"
        except FileNotFoundError:
            return True

    @contextmanager
    def _locked(self, *, exclusive: bool) -> Iterator[None]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+b") as lock_file:
            os.chmod(self.lock_path, 0o600)
            _lock_file(lock_file, exclusive=exclusive)
            try:
                yield
            finally:
                _unlock_file(lock_file)


class InMemorySessionStorage:
    """Deterministic storage useful for tests and embedded frontends."""

    def __init__(self, entries: Sequence[SessionEntry] = ()) -> None:
        self.entries = list(entries)
        self._lock = asyncio.Lock()

    async def append(self, entry: SessionEntry) -> None:
        async with self._lock:
            self.entries.append(entry)

    async def append_batch(self, entries: Sequence[SessionEntry]) -> None:
        async with self._lock:
            self.entries.extend(entries)

    async def read_all(self) -> list[SessionEntry]:
        async with self._lock:
            return list(self.entries)


def _repair_tail_bytes(data: bytes) -> tuple[bytes, bool]:
    """Return a transcript whose final line is terminated, and whether it changed.

    A partial final line is dropped when it cannot be parsed, and terminated with
    a newline when a complete record simply lost its newline.
    """
    if not data or data.endswith(b"\n"):
        return data, False
    boundary = data.rfind(b"\n") + 1
    tail = data[boundary:]
    if not tail.strip():
        return data[:boundary], True
    try:
        entry_from_json_line(tail.decode("utf-8"))
    except (SessionJsonlError, UnicodeDecodeError):
        return data[:boundary], True
    return data + b"\n", True


def _isolated_entries(entries: Sequence[SessionEntry]) -> list[SessionEntry]:
    """Return entries that do not alias the parsed cache.

    Entries, their nested messages, and custom data are mutable; a caller that
    edits a returned entry must not be able to change what future cached reads
    return without any disk write, so every read hands out fresh copies.
    """
    return [entry.model_copy(deep=True) for entry in entries]


def _appending_preserves_legacy_labels(entries: Sequence[SessionEntry]) -> bool:
    """Return whether appended entries cannot retarget migrated legacy labels.

    Target-less legacy labels resolve against the earliest branchable entry
    in the whole file (see ``entries_from_json_lines``), so appending the
    first branchable entry after such a label changes how earlier lines parse.
    """
    return any(entry.type in _BRANCHABLE_ENTRY_TYPES for entry in entries) or not any(
        entry.type == "label" for entry in entries
    )


@contextmanager
def _suppress_os_error() -> Iterator[None]:
    with suppress(OSError):
        yield


def _lock_file(file: BinaryIO, *, exclusive: bool) -> None:
    """Apply an advisory lock, with a clear unsupported-platform fallback."""
    if os.name == "nt":
        import msvcrt

        # msvcrt has no shared lock; an exclusive lock is the safe behavior for
        # reads on Windows and still provides cross-process serialization.
        del exclusive
        msvcrt.locking(file.fileno(), msvcrt.LK_LOCK, 1)  # type: ignore[attr-defined]
        return
    import fcntl

    mode = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
    fcntl.flock(file.fileno(), mode)


def _unlock_file(file: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        return
    import fcntl

    fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _fsync_directory(path: Path) -> None:
    """Persist the directory entry where the OS supports directory fsync."""
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        with suppress(OSError):
            os.fsync(descriptor)
    finally:
        os.close(descriptor)


__all__ = ["InMemorySessionStorage", "JsonlSessionStorage", "SessionStorage"]
