"""`touch_session` must not rewrite the index for a timestamp-only change.

It runs once per persisted message and each write is a temp file, fsync and
replace, so a long session used to pay one index fsync per message even when the
metadata never changed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import baldric_coding.session.manager as manager_module
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.session.manager import SessionManager


def _manager(tmp_path: Path) -> SessionManager:
    return SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))


@pytest.fixture
def index_writes(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    writes: list[Path] = []
    original = manager_module.atomic_write_text

    def recording(path: Path, content: str) -> None:
        writes.append(path)
        original(path, content)

    monkeypatch.setattr(manager_module, "atomic_write_text", recording)
    return writes


def test_a_timestamp_only_touch_does_not_rewrite_the_index(
    tmp_path: Path, index_writes: list[Path]
) -> None:
    manager = _manager(tmp_path)
    manager.create_session(cwd=tmp_path, model="m", provider_name="p")
    index_writes.clear()

    manager.touch_session(manager.list_sessions(cwd=tmp_path)[0].id, model="m", provider_name="p")

    assert index_writes == []


def test_a_metadata_change_is_written_immediately(tmp_path: Path, index_writes: list[Path]) -> None:
    manager = _manager(tmp_path)
    manager.create_session(cwd=tmp_path, model="m", provider_name="p")
    session_id = manager.list_sessions(cwd=tmp_path)[0].id
    index_writes.clear()

    manager.touch_session(session_id, model="other-model", provider_name="p")

    assert index_writes, "a model change must reach the index without waiting"
    assert manager.get_session(session_id).model == "other-model"  # type: ignore[union-attr]


def test_the_timestamp_is_written_once_the_interval_has_passed(
    tmp_path: Path, index_writes: list[Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    manager = _manager(tmp_path)
    manager.create_session(cwd=tmp_path, model="m", provider_name="p")
    session_id = manager.list_sessions(cwd=tmp_path)[0].id
    monkeypatch.setattr(manager_module, "_TOUCH_INTERVAL_SECONDS", 0.0)
    index_writes.clear()

    manager.touch_session(session_id, model="m", provider_name="p")

    assert index_writes, "the timestamp is still persisted once it is stale enough"
