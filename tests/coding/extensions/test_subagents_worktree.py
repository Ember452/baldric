"""Worktree branches the end-to-end suite does not reach.

Creation, dirty cleanup, clean removal and the non-git failure are all asserted
where the capability is loaded as an extension. What is left for this file is the
two narrower paths: a spawn started from a tracked subdirectory, and a branch
name already taken by an earlier run of the same id.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import baldric.coding.extensions.builtins.subagents.worktree as worktree_module
from baldric.coding.extensions.builtins.subagents.worktree import (
    Worktree,
    WorktreeResult,
    cleanup_worktree,
    create_worktree,
    worktree_notice,
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
    assert (worktree.path / "README.md").exists(), "the whole tree is checked out"


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


def test_worktree_notice_reports_a_saved_branch() -> None:
    notice = worktree_notice(WorktreeResult(has_changes=True, branch="baldric-agent-x"))

    assert notice is not None
    assert "git merge baldric-agent-x" in notice
    assert "preserved" not in notice


def test_worktree_notice_reports_a_preserved_worktree(tmp_path: Path) -> None:
    notice = worktree_notice(
        WorktreeResult(
            has_changes=False,
            preserved_path=tmp_path / "worktree",
            error="git add failed",
        )
    )

    assert notice is not None
    assert "preserved at" in notice
    assert "git add failed" in notice


async def test_cleanup_preserves_the_worktree_when_git_add_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    worktree = await create_worktree(repo, "addfail")
    assert worktree is not None
    (worktree.path / "mine.txt").write_text("work\n")
    original_git = worktree_module._git

    def failing_add(
        args: list[str],
        cwd: Path,
        timeout: int = worktree_module.GIT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        if args[:1] == ["add"]:
            return subprocess.CompletedProcess(["git", *args], 1, "", "add failed")
        return original_git(args, cwd, timeout)

    monkeypatch.setattr(worktree_module, "_git", failing_add)

    try:
        result = await cleanup_worktree(worktree, "add fail task")

        assert result.has_changes is False
        assert result.branch is None
        assert result.preserved_path == worktree.path
        assert result.error is not None
        assert worktree.path.exists()
        assert (worktree.path / "mine.txt").read_text(encoding="utf-8") == "work\n"
        notice = worktree_notice(result)
        assert notice is not None
        assert str(worktree.path) in notice
    finally:
        monkeypatch.undo()
        original_git(["worktree", "remove", "--force", str(worktree.path)], repo, 30)
        original_git(["worktree", "prune"], repo)


async def test_cleanup_preserves_the_worktree_when_git_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _init_git_repo(repo)
    worktree = await create_worktree(repo, "boom")
    assert worktree is not None
    (worktree.path / "mine.txt").write_text("work\n")
    original_git = worktree_module._git

    def raising_git(
        args: list[str],
        cwd: Path,
        timeout: int = worktree_module.GIT_TIMEOUT_SECONDS,
    ) -> subprocess.CompletedProcess[str]:
        if args[:1] == ["status"]:
            raise RuntimeError("git exploded")
        return original_git(args, cwd, timeout)

    monkeypatch.setattr(worktree_module, "_git", raising_git)

    try:
        result = await cleanup_worktree(worktree, "boom task")

        assert result.preserved_path == worktree.path
        assert result.error is not None
        assert "git exploded" in result.error
        assert (worktree.path / "mine.txt").read_text(encoding="utf-8") == "work\n"
    finally:
        monkeypatch.undo()
        original_git(["worktree", "remove", "--force", str(worktree.path)], repo, 30)
        original_git(["worktree", "prune"], repo)
