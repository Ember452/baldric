"""Tests for subagent settings resolution.

The behaviour cases are upstream's, ported verbatim in assertion order: project
overrides user, out-of-range and wrong-typed values are dropped and fall back to
the default (even when that discards a valid user value), `defaultMaxTurns: 0`
means unlimited, and a malformed project file is treated as absent so the user
value survives. Only the last case is new, because this host gates project files
on project trust.
"""

from __future__ import annotations

from pathlib import Path

from baldric_coding.extensions.builtins.subagents.settings import (
    SubagentSettings,
    load_subagent_settings,
)
from baldric_coding.paths import BaldricPaths


def _paths(tmp_path: Path) -> BaldricPaths:
    return BaldricPaths(home=tmp_path / "home" / ".baldric", agents_home=tmp_path / "agents")


def _load(tmp_path: Path, *, trusted: bool = True) -> SubagentSettings:
    paths = _paths(tmp_path)
    return load_subagent_settings(paths, tmp_path / "cwd", project_trusted=trusted)


def _write_user(tmp_path: Path, text: str) -> None:
    target = _paths(tmp_path).user_subagent_settings_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _write_project(tmp_path: Path, text: str) -> None:
    target = _paths(tmp_path).project_subagent_settings_path(tmp_path / "cwd")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def test_settings_defaults_overrides_and_validation(tmp_path: Path) -> None:
    defaults = _load(tmp_path)
    assert defaults == SubagentSettings()
    assert defaults.max_concurrent == 4
    assert defaults.default_max_turns is None
    assert defaults.grace_turns == 5
    assert defaults.default_join_mode == "smart"
    assert defaults.transcript_retention_days is None  # unlimited retention

    # transcriptRetentionDays: 0 (opt out) is in range; negatives are dropped.
    _write_project(tmp_path, '{"transcriptRetentionDays": 0}')
    assert _load(tmp_path).transcript_retention_days == 0
    _write_project(tmp_path, '{"transcriptRetentionDays": -1}')
    assert _load(tmp_path).transcript_retention_days is None
    _write_project(tmp_path, "{}")

    _write_user(tmp_path, '{"maxConcurrent": 8, "graceTurns": 9, "defaultJoinMode": "group"}')
    _write_project(tmp_path, '{"maxConcurrent": 2}')
    merged = _load(tmp_path)
    assert merged.max_concurrent == 2  # project overrides global
    assert merged.grace_turns == 9  # inherited from global
    assert merged.default_join_mode == "group"

    # Project sets an out-of-range int (dropped) but leaves graceTurns unset.
    _write_project(tmp_path, '{"maxConcurrent": 0, "defaultMaxTurns": 0}')
    invalid = _load(tmp_path)
    assert invalid.max_concurrent == 4  # 0 out of range dropped => default
    assert invalid.grace_turns == 9  # untouched, global value kept
    assert invalid.default_max_turns is None  # 0 => unlimited
    assert invalid.default_join_mode == "group"  # untouched global value kept

    # A wrong-typed value shadows the global and falls back to the default.
    _write_project(tmp_path, '{"graceTurns": "x"}')
    assert _load(tmp_path).grace_turns == 5

    # A boolean is not a valid int even though bool subclasses int; the
    # shadowed global is dropped too, so the field falls back to its default.
    _write_project(tmp_path, '{"maxConcurrent": true}')
    assert _load(tmp_path).max_concurrent == 4

    # Malformed project JSON is treated as empty, so only the global applies.
    _write_project(tmp_path, "not json {")
    assert _load(tmp_path).max_concurrent == 8


def test_an_untrusted_project_file_is_not_merged(tmp_path: Path) -> None:
    """Host-only case: project files are Baldric-trust-gated, user files are not."""
    _write_user(tmp_path, '{"maxConcurrent": 8}')
    _write_project(tmp_path, '{"maxConcurrent": 2, "graceTurns": 1}')

    untrusted = _load(tmp_path, trusted=False)
    trusted = _load(tmp_path, trusted=True)

    assert (untrusted.max_concurrent, untrusted.grace_turns) == (8, 5)
    assert (trusted.max_concurrent, trusted.grace_turns) == (2, 1)
