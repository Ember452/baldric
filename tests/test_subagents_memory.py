"""Tests for per-agent memory resolution and block rendering.

The behaviour cases are upstream's, ported verbatim; the only adaptation is that
`resolve_memory_dir` takes Baldric paths plus an explicit project-trust flag
instead of a bare home directory.
"""

from __future__ import annotations

from pathlib import Path

from baldric_coding.extensions.builtins.subagents.memory import (
    MEMORY_INSTRUCTIONS,
    build_memory_block,
    build_read_only_memory_block,
    is_valid_agent_name,
    read_memory_file,
    resolve_memory_dir,
)
from baldric_coding.paths import BaldricPaths


def test_memory_dir_layout_and_validation(tmp_path: Path) -> None:
    paths = BaldricPaths(home=tmp_path / "home" / ".baldric", agents_home=tmp_path / "agents")
    cwd = tmp_path / "proj"
    home_memory = paths.user_agent_memory_dir
    project_memory = paths.project_agent_memory_dir(cwd)
    local_memory = paths.project_local_agent_memory_dir(cwd)

    def resolve(scope: str, name: str, *, trusted: bool = True) -> Path | None:
        return resolve_memory_dir(scope, name, paths, cwd, project_trusted=trusted)

    assert resolve("user", "helper") == home_memory / "helper"
    assert resolve("project", "helper") == project_memory / "helper"
    assert resolve("local", "helper") == local_memory / "helper"
    assert resolve("global", "helper") is None
    assert resolve("user", "../evil") is None
    assert resolve("user", ".hidden") is None
    assert resolve("user", "a" * 129) is None

    # Host-only: project-scoped memory needs a trusted directory.
    assert resolve("project", "helper", trusted=False) is None
    assert resolve("local", "helper", trusted=False) is None
    assert resolve("user", "helper", trusted=False) == home_memory / "helper"


def test_agent_name_validation(tmp_path: Path) -> None:
    assert is_valid_agent_name("a") is True
    assert is_valid_agent_name("a" * 128) is True
    assert is_valid_agent_name("a" * 129) is False
    for rejected in ("", "-", ".x", "1/", "a b", "/abs", "../x"):
        assert is_valid_agent_name(rejected) is False, rejected


def test_memory_block_builders(tmp_path: Path) -> None:
    memory_dir = tmp_path / "mem"

    empty = build_memory_block(memory_dir, "project", None)
    assert empty.startswith("# Agent Memory\n\n")
    assert "Memory scope: project" in empty
    assert f"No MEMORY.md exists yet. Create one at {memory_dir}/MEMORY.md" in empty
    assert "MEMORY.md is your index. Keep it under 200 lines." in empty

    populated = build_memory_block(memory_dir, "user", "my notes")
    assert "## Current MEMORY.md\nmy notes" in populated

    read_only = build_read_only_memory_block(memory_dir, "user", None)
    assert read_only.startswith("# Agent Memory (read-only)")
    assert "No memory is available yet." in read_only
    assert "Memory instructions" not in read_only

    memory_dir.mkdir()
    (memory_dir / "MEMORY.md").write_text("\n".join(f"line{i}" for i in range(250)))
    content = read_memory_file(memory_dir)
    assert content.endswith("... (truncated at 200 lines)")
    assert "line199" in content
    assert "line200\n" not in content


def test_read_write_block_carries_the_instructions_and_read_only_does_not() -> None:
    memory_dir = Path("mem")

    assert MEMORY_INSTRUCTIONS in build_memory_block(memory_dir, "user", None)
    assert MEMORY_INSTRUCTIONS not in build_read_only_memory_block(memory_dir, "user", None)
