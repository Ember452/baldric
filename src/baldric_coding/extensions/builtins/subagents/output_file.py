"""JSONL output files for subagent transcripts.

Each run streams its child transcript to a durable directory under the Baldric
home so the transcript can be inspected outside the parent conversation and
survives reboots:

    ~/.baldric/subagents/<project-slug>/<parent-session>/tasks/<id>.jsonl

The `<project-slug>` component is reused verbatim from
`BaldricPaths.project_session_dir`, so a child transcript lines up with the
parent session directory for the same project instead of re-implementing the
slug and hash. Nothing parses these files back in; they are an artifact for a
person to open, which is also why they stay outside `sessions/` - the session
index must never see them.

By default transcripts are kept indefinitely. When `transcriptRetentionDays` is
positive, `sweep_transcripts` (run on session_start) deletes older ones; `0`
selects the ephemeral location under the system temp directory instead.

Write failures never propagate to the run: a transcript is a diagnostic
artifact and must not abort a child. The first failure is retained on
`OutputFileWriter.failure` so the caller can report it rather than silently
producing nothing.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from baldric_agent.messages import AgentMessage
from baldric_coding.paths import BaldricPaths

_SECONDS_PER_DAY = 86_400
_EPHEMERAL_PREFIX = "baldric-subagents"


def transcripts_root(paths: BaldricPaths) -> Path:
    """Return the durable transcript root for this Baldric home."""
    return paths.subagent_transcripts_dir


def project_dir_name(paths: BaldricPaths, cwd: Path) -> str:
    """Return the project component shared with the parent session directory."""
    return paths.project_session_dir(cwd).name


def encode_cwd(cwd: str) -> str:
    """Encode a working directory into a single, never-empty path component.

    Colons are replaced as well as separators: `C:\\proj` would otherwise become
    `C:-proj`, which is both an illegal Windows file name and something pathlib
    reads as drive-relative, silently dropping the drive and colliding two
    same-tailed projects onto one directory.
    """
    encoded = cwd.replace("/", "-").replace("\\", "-").replace(":", "-").lstrip("-")
    return encoded or "root"


def output_file_path(
    paths: BaldricPaths,
    cwd: Path,
    parent_session_id: str | None,
    agent_id: str,
    *,
    durable: bool = True,
) -> Path:
    """Return the transcript path for one run.

    Durable (default): `<transcripts root>/<project>/<session>/tasks/`.
    Ephemeral (`durable=False`, i.e. `transcriptRetentionDays: 0`): a per-uid
    directory under the system temp directory.
    """
    if durable:
        base = transcripts_root(paths) / project_dir_name(paths, cwd)
    else:
        uid = os.getuid() if hasattr(os, "getuid") else 0
        base = Path(tempfile.gettempdir()) / f"{_EPHEMERAL_PREFIX}-{uid}" / encode_cwd(str(cwd))
    return base / (parent_session_id or "no-session") / "tasks" / f"{agent_id}.jsonl"


def sweep_transcripts(
    paths: BaldricPaths,
    retention_days: int,
    *,
    now: float | None = None,
) -> int:
    """Delete durable transcripts older than `retention_days`; return the count.

    Best-effort: unreadable entries are skipped, emptied `tasks`, session and
    project directories are pruned, and the root itself is kept. Blocking -
    callers run it in a thread.
    """
    if retention_days <= 0:
        return 0
    root = transcripts_root(paths)
    if not root.is_dir():
        return 0
    cutoff = (now if now is not None else datetime.now(UTC).timestamp()) - (retention_days * _SECONDS_PER_DAY)
    removed = 0
    for transcript in root.glob("*/*/tasks/*.jsonl"):
        try:
            if transcript.stat().st_mtime < cutoff:
                transcript.unlink()
                removed += 1
        except OSError:
            continue
    # Prune now-empty directories, deepest first, never the root.
    for directory in sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()  # only succeeds when empty
        except OSError:
            continue
    return removed


class OutputFileWriter:
    """Appends transcript entries for one run to its JSONL output file."""

    def __init__(
        self,
        path: Path,
        agent_id: str,
        cwd: Path,
        *,
        inherited: int = 0,
    ) -> None:
        self.path = path
        #: Set once, at the first write that failed, so a broken transcript
        #: directory is reportable instead of invisible.
        self.failure: str | None = None
        self._agent_id = agent_id
        self._cwd = cwd
        # Index 0 is the prompt, written by write_initial. Forks additionally
        # seed `inherited` parent messages into the session; skipping them keeps
        # the whole parent transcript out of the durable file.
        self._inherited = inherited
        self._written = 1 + inherited

    async def write_initial(self, prompt: str) -> None:
        """Create the parent directories and record the child's prompt."""
        await asyncio.to_thread(self._write_initial_blocking, prompt)

    async def flush(self, messages: Sequence[AgentMessage]) -> None:
        """Append every message not written yet."""
        await asyncio.to_thread(self._flush_blocking, list(messages))

    def _write_initial_blocking(self, prompt: str) -> None:
        try:
            root = self.path.parents[3]
            root.mkdir(parents=True, exist_ok=True)
            # POSIX-only: chmod on Windows cannot express 0o700, so the
            # permission bit is best-effort and is not the protection boundary.
            os.chmod(root, 0o700)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            entry = self._entry("user", {"role": "user", "content": prompt})
            if self._inherited:
                entry["inheritedMessages"] = self._inherited
            self._append(entry)
        except OSError as exc:
            self._record_failure("write the transcript header", exc)

    def _flush_blocking(self, messages: list[AgentMessage]) -> None:
        new_messages = messages[self._written :]
        if not new_messages:
            return
        try:
            for message in new_messages:
                self._append(self._entry(message.role, _serialize_message(message)))
        except OSError as exc:
            self._record_failure("append transcript entries", exc)
            return
        self._written = len(messages)

    def _record_failure(self, action: str, exc: OSError) -> None:
        if self.failure is None:
            self.failure = f"could not {action} to {self.path}: {exc}"

    def _entry(self, entry_type: str, message: dict[str, Any]) -> dict[str, object]:
        return {
            "isSidechain": True,
            "agentId": self._agent_id,
            "type": entry_type,
            "message": message,
            "timestamp": datetime.now(UTC).isoformat(),
            "cwd": str(self._cwd),
        }

    def _append(self, entry: dict[str, object]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _serialize_message(message: AgentMessage) -> dict[str, Any]:
    return message.model_dump(mode="json")
