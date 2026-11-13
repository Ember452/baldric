"""Git worktree isolation for subagents.

A subagent spawned with `isolation: worktree` runs in a detached git worktree
of the parent repo. On completion, dirty changes are committed and preserved
on a `baldric-agent-<id>` branch in the base repo; clean worktrees are removed
without a trace. All git calls run in a thread so the event loop never blocks.
"""

from __future__ import annotations

import asyncio
import secrets
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

GIT_TIMEOUT_SECONDS = 5
WORKTREE_ADD_TIMEOUT_SECONDS = 30

WORKTREE_ERROR_MESSAGE = (
    'Cannot run with isolation: "worktree" — not a git repo, no commits yet,'
    " or git worktree add failed. Initialize git and commit at least once, or"
    " omit isolation."
)


@dataclass(frozen=True, slots=True)
class Worktree:
    """A detached worktree created for one subagent run."""

    path: Path
    branch: str
    base_sha: str
    work_path: Path
    repo: Path


@dataclass(frozen=True, slots=True)
class WorktreeResult:
    """Outcome of cleaning up a worktree after the run.

    ``error`` means the work could not be captured on a branch. The worktree is
    then deliberately kept so nothing is lost, and ``preserved_path`` tells the
    caller where it is.
    """

    has_changes: bool
    branch: str | None = None
    preserved_path: Path | None = None
    error: str | None = None


def worktree_notice(result: WorktreeResult) -> str | None:
    """Return the user-facing annotation for a cleanup outcome, if any."""
    if result.error:
        location = f" at `{result.preserved_path}`" if result.preserved_path is not None else ""
        return f"\n\n---\nSubagent worktree preserved{location}: {result.error}"
    if result.has_changes and result.branch:
        return f"\n\n---\nChanges saved to branch `{result.branch}`. Merge with: `git merge {result.branch}`"
    return None


async def create_worktree(cwd: Path, agent_id: str) -> Worktree | None:
    """Create a detached worktree of the repo containing cwd; None on failure."""
    return await asyncio.to_thread(_create_worktree_blocking, cwd, agent_id)


async def cleanup_worktree(worktree: Worktree, description: str) -> WorktreeResult:
    """Commit and preserve worktree changes on a branch, then remove it."""
    return await asyncio.to_thread(_cleanup_worktree_blocking, worktree, description)


async def prune_worktrees(repo: Path) -> None:
    """Best-effort `git worktree prune` in repo."""
    await asyncio.to_thread(_git, ["worktree", "prune"], repo)


def _create_worktree_blocking(cwd: Path, agent_id: str) -> Worktree | None:
    inside = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        return None
    head = _git(["rev-parse", "HEAD"], cwd)
    if head is None or head.returncode != 0:
        return None
    toplevel = _git(["rev-parse", "--show-toplevel"], cwd)
    if toplevel is None or toplevel.returncode != 0:
        return None
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
    if added is None or added.returncode != 0:
        return None
    work_path = path / subdir if subdir.parts else path
    return Worktree(
        path=path,
        branch=f"baldric-agent-{agent_id}",
        base_sha=head.stdout.strip(),
        work_path=work_path,
        repo=repo,
    )


def _cleanup_worktree_blocking(worktree: Worktree, description: str) -> WorktreeResult:
    try:
        if not worktree.path.exists():
            return WorktreeResult(has_changes=False)
        status = _git(["status", "--porcelain"], worktree.path)
        if status is None or status.returncode != 0:
            return _preserve(worktree, "git status failed, so its changes could not be inspected")
        if status.stdout.strip():
            added = _git(["add", "-A"], worktree.path, timeout=WORKTREE_ADD_TIMEOUT_SECONDS)
            if added is None or added.returncode != 0:
                return _preserve(worktree, "git add failed, so its changes were not committed")
            committed = _git(
                ["commit", "--no-verify", "-m", f"baldric-agent: {description[:200]}"],
                worktree.path,
                timeout=WORKTREE_ADD_TIMEOUT_SECONDS,
            )
            if committed is None or committed.returncode != 0:
                return _preserve(worktree, "git commit failed, so its changes were not committed")
        head = _git(["rev-parse", "HEAD"], worktree.path)
        if head is None or head.returncode != 0:
            raise RuntimeError("git rev-parse failed")
        if head.stdout.strip() == worktree.base_sha:
            _remove_worktree(worktree)
            return WorktreeResult(has_changes=False)
        branch = worktree.branch
        created = _git(["branch", branch], worktree.path)
        if created is None or created.returncode != 0:
            branch = f"{worktree.branch}-{int(time.time() * 1000)}"
            created = _git(["branch", branch], worktree.path)
            if created is None or created.returncode != 0:
                return _preserve(worktree, "git branch failed, so the commit has no branch yet")
        _remove_worktree(worktree)
        return WorktreeResult(has_changes=True, branch=branch)
    except Exception as exc:  # cleanup is best-effort
        return _preserve(worktree, f"worktree cleanup failed: {exc}")


def _preserve(worktree: Worktree, error: str) -> WorktreeResult:
    """Keep the worktree on disk so a failed capture cannot lose the work."""
    return WorktreeResult(has_changes=False, preserved_path=worktree.path, error=error)


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
