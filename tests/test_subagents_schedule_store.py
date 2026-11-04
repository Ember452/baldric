"""Tests for the scheduled-subagent store: persistence, validation, and locking.

The store is exercised through two independent instances over one path, because
that is the case a cached in-memory copy gets wrong, and the failure modes are
asserted to raise rather than quietly reset a user's queue.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from baldric_coding.extensions.builtins.subagents.schedule_store import (
    STORE_VERSION,
    ScheduledSubagent,
    ScheduleStore,
    ScheduleStoreError,
    resolve_store_path,
)
from baldric_coding.paths import BaldricPaths


def _job(**overrides: object) -> ScheduledSubagent:
    base: dict[str, object] = {
        "id": "job-1",
        "name": "nightly",
        "description": "run the suite",
        "schedule": "0 9 * * 1",
        "schedule_type": "cron",
        "subagent_type": "general",
        "prompt": "do the thing",
        "enabled": True,
        "created_at": "2026-11-04T09:00:00+00:00",
    }
    base.update(overrides)
    return ScheduledSubagent(**base)  # type: ignore[arg-type]


@pytest.fixture
def path(tmp_path: Path) -> Path:
    return tmp_path / "schedules" / "sess-1.json"


def _raw(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_an_absent_store_reads_empty(path: Path) -> None:
    store = ScheduleStore(path)

    assert store.list() == []
    assert store.get("job-1") is None
    assert store.has_name("nightly") is False
    # Asking must not create anything: a project that never scheduled an agent
    # would otherwise accumulate a store directory on every read.
    assert not path.exists()
    assert not path.parent.exists()


def test_add_round_trips_every_field_through_a_new_instance(path: Path) -> None:
    job = _job(
        interval_ms=60_000,
        provider="openai",
        model="gpt-x",
        thinking="high",
        max_turns=12,
        isolation="worktree",
        last_run="2026-11-03T09:00:00+00:00",
        last_status="success",
        next_run="2026-11-09T09:00:00+00:00",
        run_count=3,
    )
    ScheduleStore(path).add(job)

    reloaded = ScheduleStore(path).get("job-1")

    assert reloaded == job
    payload = _raw(path)
    assert payload["version"] == STORE_VERSION
    assert len(payload["jobs"]) == 1  # type: ignore[arg-type]
    assert job.to_json()["schedule"] == "0 9 * * 1"


def test_adding_the_same_id_replaces_the_job(path: Path) -> None:
    store = ScheduleStore(path)
    store.add(_job(name="first"))

    store.add(_job(name="second"))

    assert [job.name for job in store.list()] == ["second"]


def test_two_stores_over_one_path_never_serve_a_stale_copy(path: Path) -> None:
    """The reason every method re-reads under the lock."""
    first = ScheduleStore(path)
    second = ScheduleStore(path)

    first.add(_job(id="a"))
    second.add(_job(id="b"))

    assert sorted(job.id for job in first.list()) == ["a", "b"]


def test_remove_reports_presence_and_leaves_an_absent_id_untouched(path: Path) -> None:
    store = ScheduleStore(path)
    store.add(_job(id="a"))
    before = path.read_text(encoding="utf-8")

    assert store.remove("missing") is False
    assert path.read_text(encoding="utf-8") == before
    assert store.remove("a") is True
    assert store.list() == []


def test_update_changes_only_the_patched_fields(path: Path) -> None:
    store = ScheduleStore(path)
    store.add(_job(run_count=0, next_run=None))

    updated = store.update("job-1", run_count=1, last_status="success")

    assert updated is not None
    assert updated.run_count == 1
    assert updated.last_status == "success"
    assert updated.name == "nightly"
    assert ScheduleStore(path).get("job-1") == updated
    assert store.update("nope", run_count=5) is None


@pytest.mark.parametrize(
    "patch",
    [
        {"typo_field": "x"},
        {"name": ""},
        {"run_count": "3"},
        {"run_count": -1},
        {"run_count": True},
        {"enabled": "yes"},
        {"interval_ms": None, "max_turns": "twelve"},
    ],
)
def test_update_rejects_patches_that_would_silently_do_nothing(path: Path, patch: dict[str, object]) -> None:
    store = ScheduleStore(path)
    store.add(_job())

    with pytest.raises(ScheduleStoreError):
        store.update("job-1", **patch)

    assert ScheduleStore(path).get("job-1") is not None


def test_has_name_excludes_the_job_being_renamed(path: Path) -> None:
    store = ScheduleStore(path)
    store.add(_job(id="a", name="nightly"))

    assert store.has_name("nightly") is True
    assert store.has_name("nightly", except_id="a") is False
    assert store.has_name("weekly") is False


def test_a_corrupt_store_raises_instead_of_being_reset(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")
    store = ScheduleStore(path)

    with pytest.raises(ScheduleStoreError, match="Could not read"):
        store.list()

    # The destructive case: a mutation must not overwrite a queue it cannot read.
    with pytest.raises(ScheduleStoreError, match="Could not read"):
        store.add(_job(id="overwrite-attempt"))

    assert "not json" in path.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("payload", "fragment"),
    [
        ([1, 2], "must be a JSON object"),
        ({"version": STORE_VERSION, "jobs": [], "extra": 1}, "Unknown field"),
        ({"version": 99, "jobs": []}, "Unsupported schedule store version"),
        ({"version": STORE_VERSION, "jobs": {"a": {}}}, "must be a list"),
        ({"version": STORE_VERSION, "jobs": ["x"]}, "malformed"),
        (
            {"version": STORE_VERSION, "jobs": [{"bad": 1}]},
            "Unknown field in scheduled subagent",
        ),
        (
            {"version": STORE_VERSION, "jobs": [{**_job().to_json(), "enabled": "yes"}]},
            "'enabled' must be a boolean",
        ),
        (
            {"version": STORE_VERSION, "jobs": [{**_job().to_json(), "id": ""}]},
            "must be a non-empty string",
        ),
        (
            {
                "version": STORE_VERSION,
                "jobs": [_job().to_json(), _job().to_json()],
            },
            "Duplicate scheduled subagent id",
        ),
    ],
)
def test_malformed_documents_are_rejected(path: Path, payload: object, fragment: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ScheduleStoreError, match=fragment):
        ScheduleStore(path).list()


def test_an_atomic_write_leaves_no_temporary_and_sweeps_old_ones(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stray = path.parent / f".{path.name}.deadbeef.tmp"
    stray.write_text("interrupted write", encoding="utf-8")

    ScheduleStore(path).add(_job())

    assert not stray.exists(), "the sweep removes this store's own leftovers"
    assert list(path.parent.glob(f".{path.name}.*.tmp")) == []


def test_a_leftover_lock_file_does_not_block_the_next_process(path: Path) -> None:
    """An advisory lock dies with its holder, so no PID bookkeeping is needed.

    The ported version wrote a PID into the lock, polled 100 times, and deleted
    the file when the PID looked dead; that whole mechanism is unnecessary here.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    lock_path.write_text(str(os.getpid() + 1_000_000), encoding="utf-8")

    ScheduleStore(path).add(_job())

    assert [job.id for job in ScheduleStore(path).list()] == ["job-1"]


def test_clear_removes_the_document(path: Path) -> None:
    store = ScheduleStore(path)
    store.add(_job())

    store.clear()

    assert not path.exists()
    assert ScheduleStore(path).list() == []


def test_store_path_is_validated_before_becoming_a_file_name(tmp_path: Path) -> None:
    paths = BaldricPaths(home=tmp_path / "home", agents_home=tmp_path / "agents")
    cwd = tmp_path / "project"
    cwd.mkdir()

    resolved = resolve_store_path(paths, cwd, "sess-1")
    assert resolved.parent == paths.project_schedules_dir(cwd)
    assert resolved.name == "sess-1.json"

    for unsafe in ("", "../evil", "nested/id", "a" * 300, ".hidden"):
        with pytest.raises(ValueError):
            resolve_store_path(paths, cwd, unsafe)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes; Linux CI runs this")
def test_the_store_is_private_to_its_user(path: Path) -> None:
    store = ScheduleStore(path)
    store.add(_job())

    assert path.stat().st_mode & 0o077 == 0
    assert path.parent.stat().st_mode & 0o077 == 0
