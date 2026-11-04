"""Subagent settings for the bundled subagents capability.

Settings merge from two JSON files, the project overriding the user:

    ~/.baldric/subagents.json      user defaults
    <cwd>/.baldric/subagents.json  project overrides

Keys are camelCase: `maxConcurrent`, `defaultMaxTurns`, `graceTurns`,
`defaultJoinMode`, `transcriptRetentionDays`. Unknown keys are ignored so the
same file can be shared across Baldric upgrades and downgrades.

Two deliberate differences from the capability this was ported from:

* The project file is read only when the session's project inputs were
  approved. An untrusted repository must not be able to raise `maxConcurrent`
  or point child agents at another retention root.
* Each source is applied in turn instead of merging the raw dictionaries first.
  Merging raw values means one invalid project value overwrites a valid user
  value and then gets dropped, so the setting silently falls back to its
  default rather than to the user's own choice.

Dropped or unreadable input never raises: the caller gets the effective
settings plus one note per problem to report. Settings are read lazily in the
middle of a spawn, and a typo in an optional file must not abort a run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from baldric_coding.paths import BaldricPaths

JOIN_MODES = ("async", "group", "smart")
TRANSCRIPT_RETENTION_DAYS_DEFAULT: int | None = None


@dataclass(frozen=True, slots=True)
class SubagentSettings:
    """Effective subagent settings for one Baldric session."""

    max_concurrent: int = 4
    default_max_turns: int | None = None
    grace_turns: int = 5
    default_join_mode: str = "smart"
    # Durable transcripts live under the Baldric home. None keeps them
    # indefinitely; a positive value sweeps by age; 0 uses ephemeral storage.
    transcript_retention_days: int | None = TRANSCRIPT_RETENTION_DAYS_DEFAULT


def load_subagent_settings(
    paths: BaldricPaths,
    cwd: Path,
    *,
    project_trusted: bool = True,
) -> tuple[SubagentSettings, tuple[str, ...]]:
    """Return the effective settings and one note per dropped or unreadable input.

    `project_trusted` gates the project file only; the user file is always read.
    """
    settings = SubagentSettings()
    notes: list[str] = []
    sources: tuple[tuple[Path, bool], ...] = (
        (paths.user_subagent_settings_path, True),
        (paths.project_subagent_settings_path(cwd), project_trusted),
    )
    for path, enabled in sources:
        if not enabled:
            continue
        data, note = _read_object(path)
        if note is not None:
            notes.append(note)
        if data is None:
            continue
        settings = _apply(data, settings=settings, source=path, notes=notes)
    return settings, tuple(notes)


def _read_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Return the JSON object at `path`, or None plus a note when it can't be used."""
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # json.JSONDecodeError and UnicodeDecodeError both subclass ValueError, so
        # a non-UTF-8 file lands in the same bucket as syntactically bad JSON.
        return None, f"{path}: not readable JSON and was ignored"
    if not isinstance(raw, dict):
        return None, f"{path}: top level must be a JSON object and was ignored"
    return raw, None


def _apply(
    data: dict[str, Any],
    *,
    settings: SubagentSettings,
    source: Path,
    notes: list[str],
) -> SubagentSettings:
    """Apply one source's recognized keys over `settings`, noting what was dropped."""
    updated = settings

    max_concurrent = _int_in_range(
        data.get("maxConcurrent"), low=1, high=1024, key="maxConcurrent", source=source, notes=notes
    )
    if max_concurrent is not None:
        updated = replace(updated, max_concurrent=max_concurrent)

    # `defaultMaxTurns: 0` means "no limit", which the dataclass spells None.
    default_max_turns = _int_in_range(
        data.get("defaultMaxTurns"),
        low=0,
        high=10_000,
        key="defaultMaxTurns",
        source=source,
        notes=notes,
    )
    if default_max_turns is not None:
        updated = replace(updated, default_max_turns=None if default_max_turns == 0 else default_max_turns)

    grace_turns = _int_in_range(
        data.get("graceTurns"), low=1, high=1000, key="graceTurns", source=source, notes=notes
    )
    if grace_turns is not None:
        updated = replace(updated, grace_turns=grace_turns)

    if "defaultJoinMode" in data:
        join_mode = data["defaultJoinMode"]
        if isinstance(join_mode, str) and join_mode in JOIN_MODES:
            updated = replace(updated, default_join_mode=join_mode)
        else:
            notes.append(f"{source}: defaultJoinMode must be one of {', '.join(JOIN_MODES)} and was ignored")

    retention = _int_in_range(
        data.get("transcriptRetentionDays"),
        low=0,
        high=3650,
        key="transcriptRetentionDays",
        source=source,
        notes=notes,
    )
    if retention is not None:
        updated = replace(updated, transcript_retention_days=retention)

    return updated


def _int_in_range(
    value: object,
    *,
    low: int,
    high: int,
    key: str,
    source: Path,
    notes: list[str],
) -> int | None:
    """Return `value` when it is an in-range int; otherwise note why it was dropped."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        notes.append(f"{source}: {key} must be an integer and was ignored")
        return None
    if value < low or value > high:
        notes.append(f"{source}: {key}={value} outside {low}..{high} and was ignored")
        return None
    return value
