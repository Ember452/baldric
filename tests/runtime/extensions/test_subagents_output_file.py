"""Transcript locations and the writer, tested without a session.

Streaming a run's transcript, the retention sweep and the ephemeral fallback are
asserted by the end-to-end suite. This file covers what that suite cannot see
from outside: how a path is built from the given home, what `encode_cwd` does to
a Windows drive, and the writer's own behaviour - inherited-message skipping, an
idempotent flush, and a directory it cannot create.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from baldric.protocol.messages import AssistantMessage, UserMessage
from baldric.runtime.config.paths import BaldricPaths
from baldric.runtime.extensions.builtins.subagents.output_file import (
    OutputFileWriter,
    encode_cwd,
    output_file_path,
    project_dir_name,
    sweep_transcripts,
    transcripts_root,
)

pytestmark = pytest.mark.anyio


def _writer(path: Path, *, agent_id: str = "a1", cwd: Path | None = None, inherited: int = 0):
    return OutputFileWriter(path, agent_id, cwd or Path("cwd-marker"), inherited=inherited)


def _lines(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ── locations ────────────────────────────────────────────────────────────


def test_durable_path_mirrors_the_session_project_directory(tmp_path: Path) -> None:
    paths = BaldricPaths(home=tmp_path / "home", agents_home=tmp_path / "agents")
    cwd = tmp_path / "repos" / "app"
    cwd.mkdir(parents=True)

    result = output_file_path(cwd, "sess-9", "a1", home=paths.home)

    assert result == (paths.home / "subagents" / project_dir_name(cwd) / "sess-9" / "tasks" / "a1.jsonl")
    assert project_dir_name(cwd) == paths.project_session_dir(cwd).name
    assert result.is_relative_to(transcripts_root(paths.home))
    assert not result.is_relative_to(paths.sessions_dir)


def test_missing_parent_session_id_gets_an_explicit_component(tmp_path: Path) -> None:
    assert output_file_path(tmp_path, None, "a1", home=tmp_path / "home").parts[-3] == "no-session"


def test_encode_cwd_collapses_separators_and_never_returns_empty() -> None:
    assert encode_cwd("/") == "root"
    assert encode_cwd("") == "root"
    assert encode_cwd("/a/b/c") == "a-b-c"
    assert encode_cwd("-leading") == "leading"
    # Windows: a colon in the component is an illegal file name and makes
    # pathlib treat it as drive-relative, silently leaving the target volume.
    assert ":" not in encode_cwd("C:\\work\\app")
    assert encode_cwd("C:\\work\\app") != encode_cwd("D:\\work\\app")


def test_encode_cwd_result_stays_under_its_base() -> None:
    import tempfile

    base = Path(tempfile.gettempdir()) / "baldric-subagents-0"
    for encoded in (encode_cwd("C:\\work\\app"), encode_cwd("D:\\work\\app")):
        assert str(base / encoded).startswith(str(base)), encoded


# ── retention sweep ──────────────────────────────────────────────────────
def test_sweep_is_inert_when_there_is_no_root(tmp_path: Path) -> None:
    assert sweep_transcripts(14, tmp_path / "absent") == 0
    assert sweep_transcripts(0, tmp_path) == 0


# ── the writer itself ────────────────────────────────────────────────────


async def test_write_initial_creates_directories_and_records_the_prompt(tmp_path: Path) -> None:
    target = tmp_path / "root" / "proj" / "sess" / "tasks" / "a1.jsonl"
    writer = _writer(target, cwd=Path("cwd-marker"))

    await writer.write_initial("do the thing")

    entries = _lines(target)
    assert len(entries) == 1
    assert entries[0]["type"] == "user"
    assert entries[0]["message"] == {"role": "user", "content": "do the thing"}
    assert entries[0]["isSidechain"] is True
    assert entries[0]["agentId"] == "a1"
    assert entries[0]["cwd"] == "cwd-marker"
    assert "inheritedMessages" not in entries[0]


async def test_inherited_count_is_recorded_and_those_messages_are_skipped(
    tmp_path: Path,
) -> None:
    target = tmp_path / "root" / "proj" / "sess" / "tasks" / "f1.jsonl"
    writer = _writer(target, agent_id="f1", inherited=2)
    messages = [
        UserMessage(content="inherited"),
        AssistantMessage(),
        UserMessage(content="child"),
        AssistantMessage(),
    ]

    await writer.write_initial("child")
    await writer.flush(messages)

    entries = _lines(target)
    assert entries[0]["inheritedMessages"] == 2
    assert [entry["message"]["role"] for entry in entries[1:]] == ["assistant"]


async def test_flush_appends_only_new_messages_and_twice_is_idempotent(
    tmp_path: Path,
) -> None:
    target = tmp_path / "root" / "proj" / "sess" / "tasks" / "a1.jsonl"
    writer = _writer(target)
    await writer.write_initial("p")
    messages = [UserMessage(content="p"), AssistantMessage()]

    await writer.flush(messages)
    await writer.flush(messages)
    await writer.flush([*messages, UserMessage(content="more")])

    assert [entry["message"]["role"] for entry in _lines(target)] == ["user", "assistant", "user"]


async def test_a_broken_transcript_directory_does_not_raise(tmp_path: Path) -> None:
    blocker = tmp_path / "subagents"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("not a directory")
    writer = _writer(blocker / "proj" / "sess" / "tasks" / "a1.jsonl")

    await writer.write_initial("p")
    await writer.flush([UserMessage(content="p")])

    assert not (blocker / "proj").exists()
