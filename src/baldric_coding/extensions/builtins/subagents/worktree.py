"""Git worktree isolation for subagents.

A subagent spawned with `isolation: worktree` runs in a detached git worktree of
the parent repo. On completion, dirty changes are committed and preserved on a
`baldric-agent-<id>` branch in the base repo; clean worktrees are removed without
a trace. All git calls run in a thread so the event loop never blocks.

Three deliberate differences from the capability this was ported from:

* Failure causes are typed instead of collapsing into one message. "This is not
  a git repository", "nothing has been committed yet", "git is not installed",
  and "`git worktree add` itself failed" need different remedies, and a single
  combined hint sends the user hunting for the wrong one.
* A cleanup that fails is reported, never reported as "no changes". Silently
  returning `has_changes=False` after a failed commit or branch throwaway
  discards the child's work without telling anyone.
* A colliding branch name falls back to a random suffix, not a millisecond
  timestamp. `time.time()` granularity is coarse enough on Windows that two
  runs in the same tick still collide.
"""

from __future__ import annotations

import asyncio
import secrets
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

GIT_TIMEOUT_SECONDS = 5
WORKTREE_ADD_TIMEOUT_SECONDS = 30

#: Why a worktree could not be created. The caller turns these into user-facing
#: text; the machine-readable distinction is the point.
WorktreeFailureReason = Literal["git-missing", "not-a-repo", "no-commits", "add-failed", "add-timeout"]


@dataclass(frozen=True, slots=True)
class Worktree:
    """A detached worktree created for one subagent run."""

    path: Path
    branch: str
    base_sha: str
    work_path: Path
    repo: Path


@dataclass(frozen=True, slots=True)
class WorktreeFailure:
    """The reason no worktree could be created for this run."""

    reason: WorktreeFailureReason
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class WorktreeResult:
    """Outcome of cleaning up a worktree after the run."""

    has_changes: bool
    branch: str | None = None
    #: Set when the outcome could not be established or the work could not be
    #: preserved. `has_changes` is only an assertion when `error` is None.
    error: str | None = None


async def create_worktree(cwd: Path, agent_id: str) -> Worktree | WorktreeFailure:
    """Create a detached worktree of the repo containing cwd."""
    return await asyncio.to_thread(_create_worktree_blocking, cwd, agent_id)


async def cleanup_worktree(worktree: Worktree, description: str) -> WorktreeResult:
    """Commit and preserve worktree changes on a branch, then remove it."""
    return await asyncio.to_thread(_cleanup_worktree_blocking, worktree, description)


async def prune_worktrees(repo: Path) -> None:
    """Best-effort `git worktree prune` in repo."""
    await asyncio.to_thread(_git, ["worktree", "prune"], repo)


def _create_worktree_blocking(cwd: Path, agent_id: str) -> Worktree | WorktreeFailure:
    if shutil.which("git") is None:
        return WorktreeFailure(reason="git-missing")
    inside = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        return WorktreeFailure(reason="not-a-repo")
    head = _git(["rev-parse", "HEAD"], cwd)
    if head is None or head.returncode != 0:
        # Inside a repository, but nothing is committed, so there is no base.
        return WorktreeFailure(reason="no-commits")
    toplevel = _git(["rev-parse", "--show-toplevel"], cwd)
    if toplevel is None or toplevel.returncode != 0:
        return WorktreeFailure(reason="not-a-repo")
    repo = Path(toplevel.stdout.strip()).resolve()
    try:
        subdir = cwd.resolve().relative_to(repo)
    except ValueError:
        subdir = Path()
    path = Path(tempfile.gettempdir()) / f"baldric-agent-{agent_id}-{secrets.token_hex(4)}"
    added = _git(
        ["worktree", "add", "--detach", str(path), "HEAD"],
        cwd,
        timeout=WORKTREE_ADD_TIMEOUT_SECONDS,
    )
    if added is None:
        return WorktreeFailure(reason="add-timeout", detail=_timeout_detail(WORKTREE_ADD_TIMEOUT_SECONDS))
    if added.returncode != 0:
        return WorktreeFailure(reason="add-failed", detail=_stderr_tail(added))
    work_path = path / subdir if subdir.parts else path
    return Worktree(
        path=path,
        branch=f"baldric-agent-{agent_id}",
        base_sha=head.stdout.strip(),
        work_path=work_path,
        repo=repo,
    )


def _cleanup_worktree_blocking(worktree: Worktree, description: str) -> WorktreeResult:
    """Preserve the run's work on a branch, then remove the worktree."""
    try:
        result = _cleanup_or_raise(worktree, description)
    except _CleanupFailure as failure:
        # Keep the directory. Its changes were neither committed nor branched, so
        # removing it here would be the moment the run's work actually disappears.
        return WorktreeResult(
            has_changes=True,
            error=f"{failure}; the worktree was left at {worktree.path}",
        )
    _remove_worktree(worktree)
    return result


class _CleanupFailure(RuntimeError):
    """An internal cleanup problem with an established cause."""


def _cleanup_or_raise(worktree: Worktree, description: str) -> WorktreeResult:
    if not worktree.path.exists():
        return WorktreeResult(has_changes=False)
    status = _git(["status", "--porcelain"], worktree.path)
    if status is None:
        raise _CleanupFailure("git status timed out; the run's changes were not preserved")
    if status.returncode != 0:
        raise _CleanupFailure(f"git status failed: {_stderr_tail(status)}")
    if status.stdout.strip():
        for args in (
            ["add", "-A"],
            ["commit", "--no-verify", "-m", f"baldric-agent: {description[:200]}"],
        ):
            done = _git(args, worktree.path, timeout=WORKTREE_ADD_TIMEOUT_SECONDS)
            if done is None:
                raise _CleanupFailure(f"git {args[0]} timed out; the run's changes were not preserved")
            if done.returncode != 0:
                # A dirty worktree whose commit failed still holds the changes, but
                # they are about to be deleted with the worktree, so this is loss.
                raise _CleanupFailure(f"git {args[0]} failed: {_stderr_tail(done)}")
    head = _git(["rev-parse", "HEAD"], worktree.path)
    if head is None:
        raise _CleanupFailure("git rev-parse timed out; the run's outcome is unknown")
    if head.returncode != 0:
        raise _CleanupFailure(f"git rev-parse failed: {_stderr_tail(head)}")
    if head.stdout.strip() == worktree.base_sha:
        return WorktreeResult(has_changes=False)
    branch = worktree.branch
    created = _git(["branch", branch], worktree.path)
    if created is None:
        raise _CleanupFailure(f"git branch timed out; could not preserve {branch}")
    if created.returncode != 0:
        # The name is taken, most likely by an earlier run of the same agent id.
        branch = f"{worktree.branch}-{secrets.token_hex(3)}"
        created = _git(["branch", branch], worktree.path)
        if created is None:
            raise _CleanupFailure(f"git branch timed out; could not preserve {branch}")
        if created.returncode != 0:
            raise _CleanupFailure(f"git branch failed: {_stderr_tail(created)}")
    return WorktreeResult(has_changes=True, branch=branch)


def _remove_worktree(worktree: Worktree) -> None:
    removed = _git(
        ["worktree", "remove", "--force", str(worktree.path)],
        worktree.repo,
        timeout=WORKTREE_ADD_TIMEOUT_SECONDS,
    )
    if removed is None or removed.returncode != 0:
        _git(["worktree", "prune"], worktree.repo)


def _git(
    args: list[str], cwd: Path, timeout: int = GIT_TIMEOUT_SECONDS
) -> subprocess.CompletedProcess[str] | None:
    """Run one git command; None when it could not run to completion."""
    try:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _timeout_detail(seconds: int) -> str:
    return f"timed out after {seconds}s"


def _stderr_tail(completed: subprocess.CompletedProcess[str]) -> str:
    """Return the last stderr line, trimmed so one message stays readable."""
    lines = [line.strip() for line in (completed.stderr or "").splitlines() if line.strip()]
    if lines:
        return lines[-1][:200]
    return f"exit code {completed.returncode}"
