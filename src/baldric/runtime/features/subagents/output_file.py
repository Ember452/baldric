"""JSONL output files for subagent transcripts.

Each run streams its child transcript to a durable directory under the Baldric
home so the transcript can be inspected outside the parent conversation and
survives reboots:

    ~/.baldric/subagents/<cwd-slug>-<hash>/<parent-session>/tasks/<id>.jsonl

The directory name mirrors `BaldricPaths.project_session_dir`, which is used
directly rather than re-derived here, and lives outside `~/.baldric/sessions/` so
Baldric's session index never sees these files. By default transcripts are kept
indefinitely. When `transcriptRetentionDays` is positive, a retention sweep
(`sweep_transcripts`, run on session_start) deletes older files; setting it to 0
falls back to the old ephemeral location in the system temp directory.

The initial entry is the prompt; each `turn_end` flushes new session
messages. Write errors are swallowed and all IO runs in a thread.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from baldric.runtime.config.paths import BaldricPaths

_SECONDS_PER_DAY = 86_400


def encode_cwd(cwd: str) -> str:
    """Encode a working directory into a single, never-empty path component.

    Colons go too, not just separators: on Windows `C:\\proj` would otherwise
    become `C:-proj`, which is both an illegal file name and something pathlib
    reads as drive-relative, silently dropping the drive.
    """
    encoded = cwd.replace("/", "-").replace("\\", "-").replace(":", "-").lstrip("-")
    return encoded or "root"


def project_dir_name(cwd: Path) -> str:
    """Return `<slug>-<hash>` for a cwd, matching Baldric's session-dir naming.

    Resolved through `BaldricPaths.project_session_dir` so this stays in step
    with `~/.baldric/sessions/` for the same project instead of keeping a second
    copy of the slug and hash rule.
    """
    return BaldricPaths().project_session_dir(cwd).name


def transcripts_root(home: Path | None = None) -> Path:
    """Return the durable transcript root under the Baldric home."""
    home_dir = home if home is not None else BaldricPaths().home
    return home_dir / "subagents"


def output_file_path(
    cwd: Path,
    parent_session_id: str | None,
    agent_id: str,
    home: Path | None = None,
    *,
    durable: bool = True,
) -> Path:
    """Return the transcript path for one run.

    Durable (default): `~/.baldric/subagents/<slug>-<hash>/<session>/tasks/`.
    Ephemeral (`durable=False`, i.e. `transcriptRetentionDays: 0`): the old
    per-uid directory in the system temp dir.
    """
    if durable:
        base = transcripts_root(home) / project_dir_name(cwd)
    else:
        uid = os.getuid() if hasattr(os, "getuid") else 0
        base = Path(tempfile.gettempdir()) / f"baldric-subagents-{uid}" / encode_cwd(str(cwd))
    return base / (parent_session_id or "no-session") / "tasks" / f"{agent_id}.jsonl"


def sweep_transcripts(
    retention_days: int,
    home: Path | None = None,
    *,
    now: float | None = None,
) -> int:
    """Delete durable transcripts older than `retention_days`; return count.

    Best-effort: unreadable entries are skipped, emptied `tasks`/session/
    project directories are pruned, and the root itself is kept. Blocking -
    callers run it in a thread.
    """
    if retention_days <= 0:
        return 0
    root = transcripts_root(home)
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
        (d for d in root.rglob("*") if d.is_dir()),
        key=lambda d: len(d.parts),
        reverse=True,
    ):
        try:
            directory.rmdir()  # only succeeds when empty
        except OSError:
            continue
    return removed


class OutputFileWriter:
    """Appends transcript entries for one run to its JSONL output file."""

    def __init__(self, path: Path, agent_id: str, cwd: Path, *, inherited: int = 0) -> None:
        self.path = path
        self._agent_id = agent_id
        self._cwd = cwd
        # index 0 is the prompt, written by write_initial. Forks additionally
        # seed `inherited` parent messages into the session; skipping them
        # keeps the whole parent transcript out of the durable file.
        self._inherited = inherited
        self._written = 1 + inherited

    async def write_initial(self, prompt: str) -> None:
        await asyncio.to_thread(self._write_initial_blocking, prompt)

    async def flush(self, messages: Sequence[object]) -> None:
        await asyncio.to_thread(self._flush_blocking, list(messages))

    def _write_initial_blocking(self, prompt: str) -> None:
        try:
            root = self.path.parents[3]
            root.mkdir(parents=True, exist_ok=True)
            os.chmod(root, 0o700)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            entry = self._entry("user", {"role": "user", "content": prompt})
            if self._inherited:
                entry["inheritedMessages"] = self._inherited
            self._append(entry)
        except OSError:
            pass

    def _flush_blocking(self, messages: list[object]) -> None:
        try:
            new_messages = messages[self._written :]
            if not new_messages:
                return
            for message in new_messages:
                self._append(self._entry(_entry_type(message), _serialize_message(message)))
            self._written = len(messages)
        except OSError:
            pass

    def _entry(self, entry_type: str, message: object) -> dict[str, object]:
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


def _entry_type(message: object) -> str:
    role = getattr(message, "role", None)
    if role in ("assistant", "user"):
        return str(role)
    return "toolResult"


def _serialize_message(message: object) -> object:
    dump = getattr(message, "model_dump", None)
    if dump is not None:
        try:
            return dump(mode="json")
        except Exception:  # noqa: BLE001 - transcripts degrade to repr
            pass
    return str(message)
