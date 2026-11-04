"""Tests for git worktree isolation of subagent runs.

Covers the module contracts the ported capability tested, plus the cases it did
not: a spawn from a subdirectory, a colliding branch name, a failed commit (the
path that used to be reported as "no changes" while the work was deleted), a
`git worktree add` timeout, and the two "not usable" causes separated.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from baldric_coding.extensions.builtins.subagents import worktree as worktree_mod
from baldric_coding.extensions.builtins.subagents.worktree import (
    Worktree,
    WorktreeFailure,
    cleanup_worktree,
    create_worktree,
    prune_worktrees,
)

pytestmark = pytest.mark.anyio


def _git(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True).stdout


def _init_git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
    ):
        subprocess.run(["git", *args], cwd=path, check=True)
    (path / "README.md").write_text("hello\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=path, check=True)
    return path


async def test_create_worktree_at_repo_root(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path / "repo")

    worktree = await create_worktree(repo, "t1")

    assert isinstance(worktree, Worktree)
    assert worktree.branch == "baldric-agent-t1"
    assert worktree.work_path.exists()
    assert worktree.base_sha == _git(["rev-parse", "HEAD"], repo).strip()
    # Compare by presence, not equality: git and Windows short-path resolution can
    # spell the same directory differently, and that is not what this pins down.
    assert worktree.repo.name == repo.name
    assert (worktree.repo / "README.md").is_file()


async def test_create_worktree_from_a_subdirectory_keeps_the_repo_root(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path / "repo")
    (repo / "pkg" / "sub").mkdir(parents=True)
    # The subdirectory has to contain a tracked file: git does not store empty
    # directories, so an untracked one would legitimately be absent downstream.
    (repo / "pkg" / "sub" / "keep.md").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add subdir"], cwd=repo, check=True)

    worktree = await create_worktree(repo / "pkg" / "sub", "s1")

    assert isinstance(worktree, Worktree)
    assert worktree.work_path == worktree.path / "pkg" / "sub"
    assert worktree.work_path.exists(), "the child's cwd must exist inside the worktree"
    assert (worktree.work_path / "keep.md").read_text(encoding="utf-8") == "tracked\n"


async def test_cleanup_of_dirty_worktree_preserves_it_on_a_branch(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path / "repo")
    worktree = await create_worktree(repo, "t2")
    assert isinstance(worktree, Worktree)
    (worktree.path / "new.txt").write_text("dirty\n", encoding="utf-8")

    result = await cleanup_worktree(worktree, "my task")

    assert result.has_changes is True
    assert result.branch == "baldric-agent-t2"
    assert result.error is None
    assert not worktree.path.exists()
    assert "baldric-agent-t2" in _git(["branch", "--list", "baldric-agent-t2"], repo)
    assert _git(["log", "-1", "--format=%s", "baldric-agent-t2"], repo).strip() == ("baldric-agent: my task")


async def test_cleanup_of_clean_worktree_removes_it_without_a_branch(
    tmp_path: Path,
) -> None:
    repo = _init_git_repo(tmp_path / "repo")
    worktree = await create_worktree(repo, "t3")
    assert isinstance(worktree, Worktree)

    result = await cleanup_worktree(worktree, "nothing changed")

    assert result.has_changes is False
    assert result.branch is None
    assert not worktree.path.exists()
    assert _git(["branch", "--list", "baldric-agent-t3"], repo).strip() == ""


async def test_commit_subject_truncates_a_long_description(tmp_path: Path) -> None:
    repo = _init_git_repo(tmp_path / "repo")
    worktree = await create_worktree(repo, "t4")
    assert isinstance(worktree, Worktree)
    (worktree.path / "a.txt").write_text("x\n", encoding="utf-8")

    await cleanup_worktree(worktree, "y" * 400)

    subject = _git(["log", "-1", "--format=%s", "baldric-agent-t4"], repo).strip()
    assert subject == f"baldric-agent: {'y' * 200}"


async def test_taken_branch_name_falls_back_to_a_unique_suffix(
    tmp_path: Path,
) -> None:
    """An earlier run with the same agent id must not lose this run's work."""
    repo = _init_git_repo(tmp_path / "repo")
    worktree = await create_worktree(repo, "dup")
    assert isinstance(worktree, Worktree)
    _git(["branch", "baldric-agent-dup"], repo)  # pre-existing name
    (worktree.path / "b.txt").write_text("mine\n", encoding="utf-8")

    result = await cleanup_worktree(worktree, "dup task")

    assert result.has_changes is True
    assert result.error is None
    assert result.branch is not None
    assert result.branch != "baldric-agent-dup"
    assert result.branch.startswith("baldric-agent-dup-")
    assert _git(["branch", "--list", result.branch], repo).strip() != ""


async def test_failed_commit_is_reported_and_the_worktree_survives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The path the ported version swallowed as "no changes", losing the work."""
    repo = _init_git_repo(tmp_path / "repo")
    worktree = await create_worktree(repo, "boom")
    assert isinstance(worktree, Worktree)
    (worktree.path / "keep.txt").write_text("precious\n", encoding="utf-8")

    real_git = worktree_mod._git

    def failing_commit(
        args: list[str], cwd: Path, timeout: int = worktree_mod.GIT_TIMEOUT_SECONDS
    ) -> subprocess.CompletedProcess[str] | None:
        if args[0] == "commit":
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="hook rejected it")
        return real_git(args, cwd, timeout)

    monkeypatch.setattr(worktree_mod, "_git", failing_commit)

    result = await cleanup_worktree(worktree, "keep my work")

    assert result.error is not None
    assert "git commit failed: hook rejected it" in result.error
    assert str(worktree.path) in result.error, "the message must say where the work is"
    assert worktree.path.exists(), "cleanup must not delete unpreserved changes"
    assert (worktree.path / "keep.txt").read_text(encoding="utf-8") == "precious\n"


async def test_timed_out_worktree_add_reports_the_timeout_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_git_repo(tmp_path / "repo")

    def timing_out(args: list[str], cwd: Path, timeout: int = 5) -> None:
        if args[:2] == ["worktree", "add"]:
            return None
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)

    monkeypatch.setattr(worktree_mod, "_git", timing_out)

    failure = await create_worktree(repo, "slow")

    assert isinstance(failure, WorktreeFailure)
    assert failure.reason == "add-timeout"
    assert failure.detail is not None and "timed out" in failure.detail


async def test_non_git_directory_reports_not_a_repo(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()

    failure = await create_worktree(plain, "x1")

    assert isinstance(failure, WorktreeFailure)
    assert failure.reason == "not-a-repo"


async def test_repository_without_commits_reports_no_commits(tmp_path: Path) -> None:
    repo = tmp_path / "empty-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)

    failure = await create_worktree(repo, "x2")

    assert isinstance(failure, WorktreeFailure)
    assert failure.reason == "no-commits", "a fresh clone is fixable in a different way"


async def test_missing_git_binary_reports_its_own_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = _init_git_repo(tmp_path / "repo")
    # Replace the module's binding rather than mutating stdlib shutil, so the
    # patch cannot leak into another test running in the same process.
    monkeypatch.setattr(worktree_mod, "shutil", SimpleNamespace(which=lambda _name: None))

    failure = await create_worktree(repo, "x3")

    assert isinstance(failure, WorktreeFailure)
    assert failure.reason == "git-missing"


async def test_prune_worktrees_drops_a_stale_registration(tmp_path: Path) -> None:
    """A worktree whose directory vanished must stop showing up in `worktree list`."""
    repo = _init_git_repo(tmp_path / "repo")
    worktree = await create_worktree(repo, "stale")
    assert isinstance(worktree, Worktree)
    # Match on the directory name: `git worktree list` renders forward slashes on
    # Windows, so a str(path) containment check would fail for the wrong reason.
    before = _git(["worktree", "list"], repo)
    assert worktree.path.name in before

    shutil.rmtree(worktree.path)  # simulate a crash that left the record behind
    await prune_worktrees(repo)

    assert worktree.path.name not in _git(["worktree", "list"], repo)
