"""The project-trust gate on subagent settings files.

Defaults, overrides, out-of-range drops and malformed files are asserted by the
suite that loads the capability end to end. This covers only what that suite
cannot: the project file staying unread while the directory is untrusted.
"""

from __future__ import annotations

from pathlib import Path

from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.extensions.builtins.subagents.settings import (
    SubagentSettings,
    load_subagent_settings,
)


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


def test_an_untrusted_project_file_is_not_merged(tmp_path: Path) -> None:
    """Host-only case: project files are Baldric-trust-gated, user files are not."""
    _write_user(tmp_path, '{"maxConcurrent": 8}')
    _write_project(tmp_path, '{"maxConcurrent": 2, "graceTurns": 1}')

    untrusted = _load(tmp_path, trusted=False)
    trusted = _load(tmp_path, trusted=True)

    assert (untrusted.max_concurrent, untrusted.grace_turns) == (8, 5)
    assert (trusted.max_concurrent, trusted.grace_turns) == (2, 1)
