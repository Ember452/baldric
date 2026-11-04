"""Tests for subagent settings resolution: precedence, validation, and the trust gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from baldric_coding.extensions.builtins.subagents.settings import (
    JOIN_MODES,
    SubagentSettings,
    load_subagent_settings,
)
from baldric_coding.paths import BaldricPaths


@pytest.fixture
def paths(tmp_path: Path) -> BaldricPaths:
    return BaldricPaths(home=tmp_path / "home" / ".baldric", agents_home=tmp_path / "agents")


def _write(path: Path, data: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _load(paths: BaldricPaths, cwd: Path, *, trusted: bool = True) -> SubagentSettings:
    settings, _notes = load_subagent_settings(paths, cwd, project_trusted=trusted)
    return settings


def test_missing_files_keep_every_default(tmp_path: Path, paths: BaldricPaths) -> None:
    cwd = tmp_path / "project"

    settings, notes = load_subagent_settings(paths, cwd)

    assert settings == SubagentSettings()
    assert settings.max_concurrent == 4
    assert settings.default_max_turns is None
    assert settings.grace_turns == 5
    assert settings.default_join_mode == "smart"
    assert settings.transcript_retention_days is None
    # An absent file is the normal case, so it must not produce noise.
    assert notes == ()


def test_user_file_is_read_from_the_baldric_home(tmp_path: Path, paths: BaldricPaths) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"maxConcurrent": 9, "graceTurns": 2})

    assert _load(paths, cwd).max_concurrent == 9
    assert _load(paths, cwd).grace_turns == 2


def test_project_file_overrides_the_user_file(tmp_path: Path, paths: BaldricPaths) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"maxConcurrent": 9, "graceTurns": 2})
    _write(paths.project_subagent_settings_path(cwd), {"maxConcurrent": 1})

    settings = _load(paths, cwd)

    assert settings.max_concurrent == 1
    assert settings.grace_turns == 2, "keys the project omits stay at the user's value"


def test_untrusted_project_does_not_reach_the_settings_file(tmp_path: Path, paths: BaldricPaths) -> None:
    """A repository the user never approved cannot resize the concurrency cap."""
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"maxConcurrent": 2})
    _write(paths.project_subagent_settings_path(cwd), {"maxConcurrent": 1024})

    assert _load(paths, cwd, trusted=False).max_concurrent == 2
    assert _load(paths, cwd, trusted=True).max_concurrent == 1024


def test_invalid_project_value_does_not_evict_a_valid_user_value(tmp_path: Path, paths: BaldricPaths) -> None:
    """The per-source merge is why the user's 8 survives a broken project value.

    Merging raw dictionaries first (as the ported version did) would drop the
    key entirely and fall back to the default 4, silently losing a valid setting.
    """
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"maxConcurrent": 8})
    _write(paths.project_subagent_settings_path(cwd), {"maxConcurrent": "four"})

    settings, notes = load_subagent_settings(paths, cwd)

    assert settings.max_concurrent == 8
    assert len(notes) == 1
    assert "maxConcurrent must be an integer" in notes[0]
    assert str(paths.project_subagent_settings_path(cwd)) in notes[0], "notes must name the file"


@pytest.mark.parametrize(
    ("key", "field", "value"),
    [
        ("maxConcurrent", "max_concurrent", 0),
        ("maxConcurrent", "max_concurrent", 1025),
        ("graceTurns", "grace_turns", 0),
        ("graceTurns", "grace_turns", 1001),
        ("transcriptRetentionDays", "transcript_retention_days", 3651),
    ],
)
def test_out_of_range_values_are_dropped_with_a_range_note(
    tmp_path: Path, paths: BaldricPaths, key: str, field: str, value: int
) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {key: value})

    settings, notes = load_subagent_settings(paths, cwd)

    assert getattr(settings, field) == getattr(SubagentSettings(), field)
    assert len(notes) == 1
    assert f"{key}={value} outside" in notes[0]


def test_default_max_turns_zero_spells_no_limit(tmp_path: Path, paths: BaldricPaths) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"defaultMaxTurns": 0})

    settings, notes = load_subagent_settings(paths, cwd)

    assert settings.default_max_turns is None
    assert notes == ()

    _write(paths.user_subagent_settings_path, {"defaultMaxTurns": 12})
    assert _load(paths, cwd).default_max_turns == 12


def test_booleans_are_not_integers(tmp_path: Path, paths: BaldricPaths) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"maxConcurrent": True})

    settings, notes = load_subagent_settings(paths, cwd)

    assert settings.max_concurrent == 4
    assert "maxConcurrent must be an integer" in notes[0]


@pytest.mark.parametrize("mode", JOIN_MODES)
def test_every_join_mode_is_accepted(tmp_path: Path, paths: BaldricPaths, mode: str) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"defaultJoinMode": mode})

    assert _load(paths, cwd).default_join_mode == mode


def test_unknown_join_mode_keeps_the_current_value(tmp_path: Path, paths: BaldricPaths) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"defaultJoinMode": "group"})
    _write(paths.project_subagent_settings_path(cwd), {"defaultJoinMode": "yolo"})

    settings, notes = load_subagent_settings(paths, cwd)

    assert settings.default_join_mode == "group", "the last valid value survives"
    assert "defaultJoinMode must be one of async, group, smart" in notes[0]


def test_unknown_keys_are_ignored_for_forward_and_backward_compatibility(
    tmp_path: Path, paths: BaldricPaths
) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, {"maxConcurrent": 6, "someFutureKey": True})

    settings, notes = load_subagent_settings(paths, cwd)

    assert settings.max_concurrent == 6
    assert notes == (), "unrecognized keys are not a problem worth reporting"


def test_malformed_json_is_reported_not_raised(tmp_path: Path, paths: BaldricPaths) -> None:
    cwd = tmp_path / "project"
    paths.user_subagent_settings_path.parent.mkdir(parents=True, exist_ok=True)
    paths.user_subagent_settings_path.write_text("{not json", encoding="utf-8")

    settings, notes = load_subagent_settings(paths, cwd)

    assert settings == SubagentSettings()
    assert "not readable JSON" in notes[0]


def test_non_object_top_level_is_reported(tmp_path: Path, paths: BaldricPaths) -> None:
    cwd = tmp_path / "project"
    _write(paths.user_subagent_settings_path, [1, 2, 3])

    settings, notes = load_subagent_settings(paths, cwd)

    assert settings == SubagentSettings()
    assert "top level must be a JSON object" in notes[0]


def test_settings_follow_baldric_home_override(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """BALDRIC_HOME must move the settings file, which a hand-joined `.baldric` would not."""
    home = tmp_path / "elsewhere"
    monkeypatch.setenv("BALDRIC_HOME", str(home))
    paths = BaldricPaths()
    cwd = tmp_path / "project"
    _write(home / "subagents.json", {"maxConcurrent": 7})

    assert paths.user_subagent_settings_path == home / "subagents.json"
    assert _load(paths, cwd).max_concurrent == 7
