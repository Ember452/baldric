"""Locked, atomically replaced store for scheduled subagents.

One store file per session:

    ~/.baldric/schedules/<project-slug>/<session-id>.json

Jobs are written by the `schedule` tool and read back when a session resumes, so
this file is a queue of prompts to run later. It lives under the Baldric home for
that reason: a project tree can be committed, checked out by someone else, or
cleaned up by worktree isolation, none of which should move or leak a stored
prompt.

Concurrency follows the same shape as the llama.cpp integration state store, the
nearest existing precedent for a built-in extension's own state file: an advisory
OS lock (``fcntl.flock`` on POSIX, ``msvcrt.locking`` on Windows) around a
read-modify-write, published with ``tempfile.mkstemp`` + ``os.replace`` after an
``fsync``, private directory and file modes, and a sweep of this store's own
interrupted temporary files. Every public method takes the lock and re-reads, so
there is no in-memory copy that can go stale against another process. An
advisory lock also means no stale-lock bookkeeping: the kernel drops it when the
owning process exits, which is the case the ported PID-polling version needed a
liveness check and a takeover heuristic for.

The lock blocks. Callers running inside the event loop should offload a
mutation with ``asyncio.to_thread`` rather than call these methods directly.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager, suppress
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import IO, Any, cast

from baldric_coding.paths import BaldricPaths
from baldric_coding.session_manager import validate_session_id

STORE_VERSION = 1

#: Statuses a job can carry between runs; stored, never recomputed here.
LAST_STATUS_RUNNING = "running"
LAST_STATUS_SUCCESS = "success"
LAST_STATUS_ERROR = "error"


class ScheduleStoreError(RuntimeError):
    """Raised when a schedule store cannot be read or written safely."""


@dataclass(frozen=True, slots=True)
class ScheduledSubagent:
    """One subagent spawn registered to fire on a schedule."""

    id: str
    name: str
    description: str
    schedule: str
    schedule_type: str  # "cron" | "once" | "interval"
    subagent_type: str
    prompt: str
    enabled: bool
    created_at: str
    run_count: int = 0
    interval_ms: int | None = None
    provider: str | None = None
    model: str | None = None
    thinking: str | None = None
    max_turns: int | None = None
    isolation: str | None = None
    last_run: str | None = None
    last_status: str | None = None
    next_run: str | None = None

    def to_json(self) -> dict[str, object]:
        """Serialize this job to JSON-compatible data."""
        return asdict(self)

    @classmethod
    def from_json(cls, data: Mapping[str, object]) -> ScheduledSubagent:
        """Rebuild one job, rejecting anything this store does not own.

        A malformed file raises instead of being skipped: silently dropping a job
        would erase it on the next save, and silently starting fresh would erase
        every job in the file.
        """
        known = {field.name for field in fields(cls)}
        unknown = set(data) - known
        if unknown:
            raise ScheduleStoreError(f"Unknown field in scheduled subagent: {sorted(unknown)[0]}")
        for required in ("id", "name", "description", "schedule", "schedule_type", "subagent_type", "prompt"):
            _require_str(data, required)
        _require_str(data, "created_at")
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            raise ScheduleStoreError("Scheduled subagent field 'enabled' must be a boolean")
        run_count = data.get("run_count", 0)
        if not _is_count(run_count):
            raise ScheduleStoreError("Scheduled subagent field 'run_count' must be a non-negative integer")
        for optional in ("provider", "model", "thinking", "isolation", "last_run", "last_status", "next_run"):
            _require_str_or_none(data, optional)
        for optional_int in ("interval_ms", "max_turns"):
            value = data.get(optional_int)
            if value is not None and not _is_count(value):
                raise ScheduleStoreError(
                    f"Scheduled subagent field {optional_int!r} must be a non-negative integer or null"
                )
        return cls(
            id=cast(str, data["id"]),
            name=cast(str, data["name"]),
            description=cast(str, data["description"]),
            schedule=cast(str, data["schedule"]),
            schedule_type=cast(str, data["schedule_type"]),
            subagent_type=cast(str, data["subagent_type"]),
            prompt=cast(str, data["prompt"]),
            enabled=enabled,
            created_at=cast(str, data["created_at"]),
            run_count=cast(int, run_count),
            interval_ms=cast("int | None", data.get("interval_ms")),
            provider=cast("str | None", data.get("provider")),
            model=cast("str | None", data.get("model")),
            thinking=cast("str | None", data.get("thinking")),
            max_turns=cast("int | None", data.get("max_turns")),
            isolation=cast("str | None", data.get("isolation")),
            last_run=cast("str | None", data.get("last_run")),
            last_status=cast("str | None", data.get("last_status")),
            next_run=cast("str | None", data.get("next_run")),
        )


def _require_str(data: Mapping[str, object], name: str) -> str:
    value = data.get(name)
    if not isinstance(value, str) or not value:
        raise ScheduleStoreError(f"Scheduled subagent field {name!r} must be a non-empty string")
    return value


def _require_str_or_none(data: Mapping[str, object], name: str) -> None:
    value = data.get(name)
    if value is not None and not isinstance(value, str):
        raise ScheduleStoreError(f"Scheduled subagent field {name!r} must be a string or null")


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def schedule_store_path(paths: BaldricPaths, cwd: Path, session_id: str) -> Path:
    """Return the store path for one session, rejecting unsafe session ids.

    Session ids are user-supplied for ``/new --name`` style flows, so they go
    through Baldric's existing session-id validation before becoming a file name.
    """
    validate_session_id(session_id)
    return paths.project_schedules_dir(cwd) / f"{session_id}.json"


class SubagentScheduleStore:
    """Session-scoped, OS-locked, atomically replaced store of scheduled subagents."""

    def __init__(self, path: Path, *, lock_path: Path | None = None) -> None:
        self.path = path
        self.lock_path = lock_path or path.with_name(f"{path.name}.lock")

    def list(self) -> list[ScheduledSubagent]:
        """Return every job, in the order they are stored."""
        return list(self._read().values())

    def get(self, job_id: str) -> ScheduledSubagent | None:
        """Return one job by id."""
        return self._read().get(job_id)

    def has_name(self, name: str, *, except_id: str | None = None) -> bool:
        """Return True when another job already uses this name."""
        jobs = self._read()
        return any(job.id != except_id and job.name == name for job in jobs.values())

    def add(self, job: ScheduledSubagent) -> None:
        """Insert one job, replacing any job that already has its id."""
        with self._locked():
            jobs = self._read_unlocked()
            jobs[job.id] = job
            self._write_unlocked(jobs)

    def update(self, job_id: str, **patch: object) -> ScheduledSubagent | None:
        """Apply a field patch to one job; None when the job is not stored.

        The merged job is rebuilt through `from_json`, so a patch is validated
        exactly like a stored job: an unknown key, an empty name, or a
        non-numeric `run_count` raises instead of writing a job that quietly
        ignores what the caller meant to change.
        """
        with self._locked():
            jobs = self._read_unlocked()
            existing = jobs.get(job_id)
            if existing is None:
                return None
            updated = ScheduledSubagent.from_json({**existing.to_json(), **patch})
            jobs[job_id] = updated
            self._write_unlocked(jobs)
            return updated

    def remove(self, job_id: str) -> bool:
        """Remove one job; return whether it was stored."""
        with self._locked():
            jobs = self._read_unlocked()
            if jobs.pop(job_id, None) is None:
                return False
            self._write_unlocked(jobs)
            return True

    def clear(self) -> None:
        """Remove the whole store file, leaving an empty set for future reads."""
        with self._locked():
            if self.path.exists():
                self.path.unlink()
                _fsync_directory(self.path.parent)

    def _read(self) -> dict[str, ScheduledSubagent]:
        """Return the stored jobs, without touching disk when there are none.

        A missing file is the common case (every project that never scheduled an
        agent), so it short-circuits: taking the lock would create the store
        directory just for asking whether jobs exist.
        """
        if not self.path.exists():
            return {}
        with self._locked():
            return self._read_unlocked()

    @contextmanager
    def _locked(self) -> Iterator[None]:
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            with self.lock_path.open("a+b") as handle:
                self.lock_path.chmod(0o600)
                _lock(handle)
                try:
                    _remove_stale_temporaries(self.path)
                    yield
                finally:
                    _unlock(handle)
        except OSError as exc:
            raise ScheduleStoreError(f"Could not access the schedule store: {exc}") from exc

    def _read_unlocked(self) -> dict[str, ScheduledSubagent]:
        if not self.path.exists():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ScheduleStoreError(f"Could not read the schedule store: {exc}") from exc
        if not isinstance(payload, dict):
            raise ScheduleStoreError("The schedule store must be a JSON object")
        if set(payload) - {"version", "jobs"}:
            raise ScheduleStoreError("Unknown field in the schedule store")
        if payload.get("version") != STORE_VERSION:
            raise ScheduleStoreError("Unsupported schedule store version")
        raw_jobs = payload.get("jobs", [])
        if not isinstance(raw_jobs, list):
            raise ScheduleStoreError("Scheduled subagents must be a list")
        jobs: dict[str, ScheduledSubagent] = {}
        for raw in raw_jobs:
            if not isinstance(raw, dict):
                raise ScheduleStoreError("Scheduled subagent is malformed")
            job = ScheduledSubagent.from_json(raw)
            if job.id in jobs:
                raise ScheduleStoreError(f"Duplicate scheduled subagent id: {job.id}")
            jobs[job.id] = job
        return jobs

    def _write_unlocked(self, jobs: Mapping[str, ScheduledSubagent]) -> None:
        payload = {
            "version": STORE_VERSION,
            "jobs": [job.to_json() for job in jobs.values()],
        }
        data = (json.dumps(payload, indent=2) + "\n").encode("utf-8")
        temporary: Path | None = None
        descriptor = -1
        try:
            descriptor, raw = tempfile.mkstemp(
                prefix=f".{self.path.name}.", suffix=".tmp", dir=self.path.parent
            )
            temporary = Path(raw)
            temporary.chmod(0o600)
            with os.fdopen(descriptor, "wb") as handle:
                descriptor = -1
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
            temporary = None
            self.path.chmod(0o600)
            _fsync_directory(self.path.parent)
        except OSError as exc:
            raise ScheduleStoreError(f"Could not write the schedule store: {exc}") from exc
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary is not None:
                with suppress(OSError):
                    temporary.unlink()


def _remove_stale_temporaries(path: Path) -> None:
    """Delete only this store's own interrupted atomic-write leftovers."""
    for leftover in path.parent.glob(f".{path.name}.*.tmp"):
        with suppress(OSError):
            leftover.unlink()


def _lock(handle: IO[Any]) -> None:
    try:
        import fcntl
    except ImportError:
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)  # type: ignore[attr-defined]


def _unlock(handle: IO[Any]) -> None:
    try:
        import fcntl
    except ImportError:
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def _fsync_directory(path: Path) -> None:
    with suppress(OSError):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


__all__ = [
    "LAST_STATUS_ERROR",
    "LAST_STATUS_RUNNING",
    "LAST_STATUS_SUCCESS",
    "STORE_VERSION",
    "ScheduledSubagent",
    "SubagentScheduleStore",
    "schedule_store_path",
]
