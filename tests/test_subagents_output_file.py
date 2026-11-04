"""Tests for the durable subagent transcript writer and its retention sweep.

Covers the layout, the fork `inherited` offset, per-role entry typing, the
age-bounded sweep on an injected clock, and that a broken transcript directory
becomes a reportable failure instead of either silence or an aborted run.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from baldric_agent.messages import (
    AssistantMessage,
    BashExecutionMessage,
    BranchSummaryMessage,
    CustomMessage,
    ToolResultMessage,
    UserMessage,
)
from baldric_coding.extensions.builtins.subagents.output_file import (
    OutputFileWriter,
    encode_cwd,
    output_file_path,
    project_dir_name,
    sweep_transcripts,
    transcripts_root,
)
from baldric_coding.paths import BaldricPaths

pytestmark = pytest.mark.anyio


@pytest.fixture
def paths(tmp_path: Path) -> BaldricPaths:
    return BaldricPaths(home=tmp_path / "home" / ".baldric", agents_home=tmp_path / "agents")


@pytest.fixture
def cwd(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    return project


def _lines(path: Path) -> list[dict[object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _writer(
    path: Path, *, agent_id: str = "agent-1", inherited: int = 0, cwd: Path | None = None
) -> OutputFileWriter:
    # A platform-neutral default cwd: str(Path("/cwd")) renders "\\cwd" on
    # Windows, which would fail the recorded-cwd assertion for the wrong reason.
    return OutputFileWriter(path, agent_id, cwd or Path("cwd-marker"), inherited=inherited)


def test_durable_path_mirrors_the_parent_session_directory(paths: BaldricPaths, cwd: Path) -> None:
    result = output_file_path(paths, cwd, "sess-9", "agent-1")

    assert result == (
        paths.subagent_transcripts_dir / project_dir_name(paths, cwd) / "sess-9" / "tasks" / "agent-1.jsonl"
    )
    # The project component is the session directory's own name, not a re-derivation.
    assert project_dir_name(paths, cwd) == paths.project_session_dir(cwd).name
    assert result.is_relative_to(transcripts_root(paths))
    assert not result.is_relative_to(paths.sessions_dir), "the session index must never see these"


def test_missing_parent_session_id_gets_an_explicit_component(paths: BaldricPaths, cwd: Path) -> None:
    assert output_file_path(paths, cwd, None, "a1").parts[-3] == "no-session"


def test_retention_zero_writes_under_the_temporary_root_and_not_the_home(
    tmp_path: Path, paths: BaldricPaths, cwd: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_temp = tmp_path / "tmpdir"
    fake_temp.mkdir()
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(fake_temp))

    result = output_file_path(paths, cwd, "sess-1", "a1", durable=False)

    assert not result.is_relative_to(paths.home)
    assert "baldric-subagents-" in str(result)
    assert encode_cwd(str(cwd)) in result.parts


def test_encode_cwd_collapses_separators_and_never_returns_empty() -> None:
    assert encode_cwd("/a/b/c") == "a-b-c"
    assert encode_cwd("C:\\x\\y") == "C--x-y"
    assert encode_cwd("-leading") == "leading"
    assert encode_cwd("/") == "root"
    assert encode_cwd("") == "root"


def test_encode_cwd_keeps_different_drives_apart() -> None:
    """A colon in the component collapsed to drive-relative and collided before."""
    assert encode_cwd("C:\\work\\app") != encode_cwd("D:\\work\\app")
    for encoded in (encode_cwd("C:\\work\\app"), encode_cwd("D:\\work\\app")):
        assert ":" not in encoded
        assert encoded.strip("-") != ""


async def test_write_initial_creates_directories_and_records_the_prompt(
    paths: BaldricPaths, cwd: Path
) -> None:
    target = output_file_path(paths, cwd, "sess-1", "a1")
    writer = _writer(target, agent_id="a1")

    await writer.write_initial("do the thing")

    lines = _lines(target)
    assert len(lines) == 1
    entry = lines[0]
    assert entry["type"] == "user"
    assert entry["message"] == {"role": "user", "content": "do the thing"}
    assert entry["isSidechain"] is True
    assert entry["agentId"] == "a1"
    assert entry["cwd"] == "cwd-marker"
    assert "inheritedMessages" not in entry
    assert target.parent.is_dir()


async def test_inherited_count_is_recorded_and_skipped_by_flush(paths: BaldricPaths, cwd: Path) -> None:
    """A fork seeds parent history into the child session; only new turns get logged."""
    target = output_file_path(paths, cwd, "sess-1", "fork-1")
    writer = _writer(target, inherited=2)
    messages = [
        UserMessage(content="inherited prompt"),
        AssistantMessage(),
        UserMessage(content="child prompt"),
        AssistantMessage(),
    ]

    await writer.write_initial("child prompt")
    await writer.flush(messages)

    lines = _lines(target)
    assert lines[0]["inheritedMessages"] == 2
    assert [line["message"]["role"] for line in lines[1:]] == ["assistant"], "only the new turn"


async def test_flush_appends_each_unseen_message_once_and_is_idempotent(
    paths: BaldricPaths, cwd: Path
) -> None:
    target = output_file_path(paths, cwd, "sess-1", "a1")
    writer = _writer(target)
    await writer.write_initial("p")

    first = [UserMessage(content="p"), AssistantMessage()]
    await writer.flush(first)
    await writer.flush(first)
    await writer.flush([*first, ToolResultMessage(tool_call_id="c1", tool_name="bash")])

    lines = _lines(target)
    assert [line["message"]["role"] for line in lines] == ["user", "assistant", "toolResult"]


async def test_entry_type_follows_the_actual_role_for_every_message_kind(
    paths: BaldricPaths, cwd: Path
) -> None:
    """The ported classifier collapsed anything but user/assistant into toolResult."""
    target = output_file_path(paths, cwd, "sess-1", "a1")
    writer = _writer(target, agent_id="a1")
    messages = [
        UserMessage(content="p"),
        BashExecutionMessage(command="ls", output="ok"),
        CustomMessage(custom_type="reminder", content="note"),
        BranchSummaryMessage(summary="recap", from_id="m0"),
        ToolResultMessage(tool_call_id="c1", tool_name="read"),
    ]

    await writer.write_initial("p")
    await writer.flush(messages)

    assert [line["type"] for line in _lines(target)] == [
        "user",  # the write_initial header
        "bashExecution",
        "custom",
        "branchSummary",
        "toolResult",
    ]
    assert _lines(target)[1:][0]["message"]["command"] == "ls"


def test_sweep_deletes_only_expired_entries_and_prunes_empty_dirs(
    paths: BaldricPaths, tmp_path: Path
) -> None:
    root = transcripts_root(paths)
    old = root / "proj-a" / "sess-1" / "tasks" / "old.jsonl"
    fresh = root / "proj-b" / "sess-2" / "tasks" / "new.jsonl"
    for target in (old, fresh):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}\n", encoding="utf-8")
    day = 86_400
    now = 1_700_000_000.0
    os.utime(old, (now - 10 * day, now - 10 * day))
    os.utime(fresh, (now - day, now - day))

    removed = sweep_transcripts(paths, retention_days=7, now=now)

    assert removed == 1
    assert not old.exists()
    assert fresh.exists()
    assert old.parents[2].exists() is False, "the emptied project directory is pruned"
    assert root.is_dir(), "the root itself is never removed"


def test_sweep_is_inert_for_non_positive_retention_and_a_missing_root(
    tmp_path: Path,
) -> None:
    paths = BaldricPaths(home=tmp_path / "absent", agents_home=tmp_path / "agents")

    assert sweep_transcripts(paths, retention_days=0, now=1.0) == 0
    assert sweep_transcripts(paths, retention_days=-1, now=1.0) == 0
    assert sweep_transcripts(paths, retention_days=7, now=1.0) == 0
    assert not transcripts_root(paths).exists()


def test_sweep_skips_entries_it_cannot_remove(tmp_path: Path) -> None:
    paths = BaldricPaths(home=tmp_path / "home", agents_home=tmp_path / "agents")
    tasks = transcripts_root(paths) / "proj" / "sess" / "tasks"
    tasks.mkdir(parents=True)
    (tasks / "unreadable.jsonl").mkdir()  # a directory sitting in the glob's way

    assert sweep_transcripts(paths, retention_days=1, now=10_000_000_000.0) == 0


async def test_unwritable_transcript_directory_reports_once_and_never_raises(
    tmp_path: Path, paths: BaldricPaths, cwd: Path
) -> None:
    """A transcript failure must not abort the child, and must not be invisible."""
    blocker = transcripts_root(paths)
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("not a directory", encoding="utf-8")  # mkdir will conflict
    writer = _writer(blocker / "proj" / "sess" / "tasks" / "a1.jsonl")

    await writer.write_initial("p")  # must not raise
    await writer.flush([UserMessage(content="p")])

    assert writer.failure is not None
    assert "could not write the transcript header" in writer.failure
    assert str(writer.path) in writer.failure
    first_failure = writer.failure
    await writer.flush([UserMessage(content="p"), AssistantMessage()])
    assert writer.failure == first_failure, "the first cause is kept, not overwritten"
