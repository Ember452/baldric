"""Tests for per-agent memory resolution, the trust gate, and block rendering."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from baldric_coding.extensions.builtins.subagents.memory import (
    MAX_MEMORY_LINES,
    MEMORY_INSTRUCTIONS,
    MEMORY_TRUNCATION_SUFFIX,
    build_memory_block,
    build_read_only_memory_block,
    is_valid_agent_name,
    prepare_memory,
    read_memory_file,
    resolve_memory_dir,
)
from baldric_coding.paths import BaldricPaths

pytestmark = pytest.mark.anyio

LONG_NAME = "n" * 129


@pytest.fixture
def paths(tmp_path: Path) -> BaldricPaths:
    return BaldricPaths(home=tmp_path / "home" / ".baldric", agents_home=tmp_path / "agents")


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def test_three_scopes_resolve_to_three_roots(paths: BaldricPaths, cwd: Path) -> None:
    user = resolve_memory_dir("user", "scout", paths, cwd, project_trusted=True)
    project = resolve_memory_dir("project", "scout", paths, cwd, project_trusted=True)
    local = resolve_memory_dir("local", "scout", paths, cwd, project_trusted=True)

    assert user == paths.user_agent_memory_dir / "scout"
    assert project == paths.project_agent_memory_dir(cwd) / "scout"
    assert local == paths.project_local_agent_memory_dir(cwd) / "scout"
    assert len({user, project, local}) == 3


def test_unknown_scope_and_bad_name_resolve_to_nothing(paths: BaldricPaths, cwd: Path) -> None:
    assert resolve_memory_dir("global", "scout", paths, cwd, project_trusted=True) is None
    assert resolve_memory_dir("user", "../escape", paths, cwd, project_trusted=True) is None


def test_project_scopes_are_blocked_when_untrusted_but_user_is_not(paths: BaldricPaths, cwd: Path) -> None:
    assert resolve_memory_dir("project", "scout", paths, cwd, project_trusted=False) is None
    assert resolve_memory_dir("local", "scout", paths, cwd, project_trusted=False) is None
    assert (
        resolve_memory_dir("user", "scout", paths, cwd, project_trusted=False)
        == paths.user_agent_memory_dir / "scout"
    )


@pytest.mark.parametrize(
    ("name", "valid"),
    [
        ("scout", True),
        ("agent-1", True),
        ("a.b_c-d", True),
        ("9lives", True),
        ("x" * 128, True),
        (LONG_NAME, False),
        ("", False),
        (".hidden", False),
        ("../escape", False),
        ("nested/name", False),
        ("with space", False),
        ("trailing-", True),
    ],
)
def test_agent_name_is_confined_to_one_safe_path_component(name: str, valid: bool) -> None:
    assert is_valid_agent_name(name) is valid


def test_read_memory_file_returns_none_when_absent(tmp_path: Path) -> None:
    assert read_memory_file(tmp_path / "nowhere") is None


def test_read_memory_file_truncates_at_the_line_cap(tmp_path: Path) -> None:
    directory = tmp_path / "mem"
    directory.mkdir()
    (directory / "MEMORY.md").write_text(
        "\n".join(f"line {index}" for index in range(MAX_MEMORY_LINES + 5)), encoding="utf-8"
    )

    text = read_memory_file(directory)

    assert text is not None
    assert text.endswith(MEMORY_TRUNCATION_SUFFIX)
    assert len(text.splitlines()) == MAX_MEMORY_LINES + 1  # suffix is on the last line


def test_read_memory_file_treats_a_non_utf8_index_as_absent(tmp_path: Path) -> None:
    directory = tmp_path / "mem"
    directory.mkdir()
    (directory / "MEMORY.md").write_bytes(b"\xff\xfe not utf-8")

    assert read_memory_file(directory) is None


def test_memory_blocks_name_the_directory_and_their_promises_differ() -> None:
    directory = Path("/base/mem/scout")

    read_write = build_memory_block(directory, "user", "existing index")
    fresh = build_memory_block(directory, "user", None)
    read_only = build_read_only_memory_block(directory, "user", None)

    # Asserted through str(Path) so the same test is exact on POSIX and Windows.
    assert str(directory) in read_write
    assert "Memory scope: user" in read_write
    assert MEMORY_INSTRUCTIONS in read_write
    assert "## Current MEMORY.md\nexisting index" in read_write

    assert f"Create one at {directory / 'MEMORY.md'}" in fresh
    assert "## Current MEMORY.md" not in fresh

    assert "(read-only)" in read_only
    assert "do not modify it" in read_only
    assert "No memory is available yet." in read_only
    assert str(directory) in read_only
    assert MEMORY_INSTRUCTIONS not in read_only


async def test_read_write_prepare_creates_the_directory(paths: BaldricPaths, cwd: Path) -> None:
    outcome = await prepare_memory("scout", "user", paths, cwd, read_write=True, project_trusted=True)

    assert outcome.reason is None
    assert outcome.block is not None
    assert (paths.user_agent_memory_dir / "scout").is_dir()


async def test_read_only_prepare_does_not_create_anything(paths: BaldricPaths, cwd: Path) -> None:
    outcome = await prepare_memory("ghost", "user", paths, cwd, read_write=False, project_trusted=True)

    assert outcome.block is not None
    assert "(read-only)" in outcome.block
    assert not (paths.user_agent_memory_dir / "ghost").exists()


async def test_prepare_includes_an_existing_index(paths: BaldricPaths, cwd: Path) -> None:
    directory = paths.user_agent_memory_dir / "scout"
    directory.mkdir(parents=True)
    (directory / "MEMORY.md").write_text("# notes\n- prefer pytest\n", encoding="utf-8")

    outcome = await prepare_memory("scout", "user", paths, cwd, read_write=True, project_trusted=True)

    assert "- prefer pytest" in (outcome.block or "")


@pytest.mark.parametrize("scope", ["project", "local"])
async def test_untrusted_project_prepare_reports_the_gate(scope: str, paths: BaldricPaths, cwd: Path) -> None:
    outcome = await prepare_memory("scout", scope, paths, cwd, read_write=True, project_trusted=False)

    assert outcome.block is None
    assert outcome.reason is not None
    assert scope in outcome.reason
    assert "trust" in outcome.reason
    assert not (
        paths.project_baldric_dir(cwd) / f"agent-memory{'-local' if scope == 'local' else ''}"
    ).exists()


async def test_prepare_reports_no_block_and_no_reason_for_no_scope(paths: BaldricPaths, cwd: Path) -> None:
    outcome = await prepare_memory("scout", None, paths, cwd, read_write=True, project_trusted=True)

    assert outcome.block is None
    assert outcome.reason is None, "not requesting memory is not a problem"


async def test_prepare_reports_an_unknown_scope(paths: BaldricPaths, cwd: Path) -> None:
    outcome = await prepare_memory("scout", "global", paths, cwd, read_write=True, project_trusted=True)

    assert outcome.block is None
    assert "must be one of user, project, local" in (outcome.reason or "")


async def test_prepare_reports_an_unusable_name(paths: BaldricPaths, cwd: Path) -> None:
    outcome = await prepare_memory("../escape", "user", paths, cwd, read_write=True, project_trusted=True)

    assert outcome.block is None
    assert "cannot be used as a memory directory" in (outcome.reason or "")


async def test_prepare_reports_a_directory_it_cannot_create(
    paths: BaldricPaths, cwd: Path, tmp_path: Path
) -> None:
    blocker = tmp_path / "home" / ".baldric" / "agent-memory"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("a file where a directory belongs", encoding="utf-8")

    outcome = await prepare_memory("scout", "user", paths, cwd, read_write=True, project_trusted=True)

    assert outcome.block is None
    assert "could not create" in (outcome.reason or "")


async def test_a_symlinked_memory_directory_is_refused(
    paths: BaldricPaths, cwd: Path, tmp_path: Path
) -> None:
    """The guard exists so a planted link cannot redirect writes elsewhere."""
    if sys.platform == "win32":
        pytest.skip("symlink privileges not granted on Windows; Linux CI runs this")
    outside = tmp_path / "outside"
    outside.mkdir()
    link = paths.user_agent_memory_dir / "scout"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(outside, target_is_directory=True)

    resolved = resolve_memory_dir("user", "scout", paths, cwd, project_trusted=True)

    assert resolved is None

    outcome = await prepare_memory("scout", "user", paths, cwd, read_write=True, project_trusted=True)
    assert outcome.block is None
    assert "symlink" in (outcome.reason or "")
    assert not (outside / "MEMORY.md").exists()
