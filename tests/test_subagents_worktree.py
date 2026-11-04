"""Tests for git worktree isolation of subagent runs.

The two cases here are upstream's, ported verbatim apart from the branch and
commit-message prefix; the two after them cover branches its suite does not
reach: a spawn from a tracked subdirectory, and a branch name already taken by
an earlier run of the same id.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from baldric_coding.extensions.builtins.subagents.worktree import (
    Worktree,
    cleanup_worktree,
    create_worktree,
)

pytestmark = pytest.mark.anyio


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *args], cwd=path, check=True)
    (path / "README.md").write_text("hello\n")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)


def _git_stdout(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


async def test_worktree_create_and_cleanup_dirty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)

    worktree = await create_worktree(repo, "t1")
    assert worktree is not None
    assert worktree.branch == "baldric-agent-t1"
    assert worktree.work_path.exists()
    assert worktree.repo == repo.resolve()

    (worktree.path / "new.txt").write_text("dirty\n")
    result = await cleanup_worktree(worktree, "my task")

    assert result.has_changes is True
    assert result.branch == "baldric-agent-t1"
    assert not worktree.path.exists()
    assert "baldric-agent-t1" in _git_stdout(["branch", "--list", "baldric-agent-t1"], repo)
    message = _git_stdout(["log", "-1", "--format=%s", "baldric-agent-t1"], repo)
    assert message.strip() == "baldric-agent: my task"


async def test_worktree_cleanup_clean_removes_without_branch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)

    worktree = await create_worktree(repo, "t2")
    assert worktree is not None
    result = await cleanup_worktree(worktree, "task")

    assert result.has_changes is False
    assert not worktree.path.exists()
    assert _git_stdout(["branch", "--list", "baldric-agent-t2"], repo).strip() == ""

    plain = tmp_path / "plain"
    plain.mkdir()
    assert await create_worktree(plain, "t3") is None


async def test_worktree_from_a_subdirectory_keeps_the_repo_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    (repo / "pkg" / "sub").mkdir(parents=True)
    (repo / "pkg" / "sub" / "keep.md").write_text("tracked\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add subdir"], cwd=repo, check=True)

    worktree = await create_worktree(repo / "pkg" / "sub", "s1")

    assert isinstance(worktree, Worktree)
    assert worktree.work_path == worktree.path / "pkg" / "sub"
    assert (worktree.work_path / "keep.md").read_text() == "tracked\n"
    assert (worktree.path / "README.md").exists(), "the checkout holds the whole tree, not just the subdirectory"


async def test_a_taken_branch_name_falls_back_to_a_timed_suffix(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    worktree = await create_worktree(repo, "dup")
    assert worktree is not None
    _git_stdout(["branch", "baldric-agent-dup"], repo)
    (worktree.path / "mine.txt").write_text("work\n")

    result = await cleanup_worktree(worktree, "dup task")

    assert result.has_changes is True
    assert result.branch is not None
    assert result.branch != "baldric-agent-dup"
    assert result.branch.startswith("baldric-agent-dup-")
    assert _git_stdout(["branch", "--list", result.branch], repo).strip() != ""
