"""External prompt-editor resolution and invocation."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from baldric.runtime.frontends.tui.editor import (
    EditorError,
    edit_prompt_text,
    resolve_editor_command,
)


def test_resolve_prefers_settings_over_environment() -> None:
    argv = resolve_editor_command(
        "code -w",
        environ={"BALDRIC_EDITOR": "vim", "VISUAL": "nano", "EDITOR": "ed"},
    )
    assert argv == ["code", "-w"]


def test_resolve_falls_back_to_environment_order() -> None:
    argv = resolve_editor_command(
        None,
        environ={"VISUAL": "nano", "EDITOR": "ed", "BALDRIC_EDITOR": "vim"},
    )
    assert argv == ["vim"]


def test_resolve_ignores_blank_values() -> None:
    argv = resolve_editor_command("  ", environ={"BALDRIC_EDITOR": "  ", "EDITOR": "micro"})
    assert argv == ["micro"]


def test_resolve_splits_quoted_windows_paths() -> None:
    argv = resolve_editor_command('"C:\\Program Files\\Editor\\ed.exe" -w', environ={})
    assert argv == ["C:\\Program Files\\Editor\\ed.exe", "-w"]


def test_resolve_falls_back_to_platform_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("os.name", "posix")
    assert resolve_editor_command(None, environ={}) == ["vi"]
    monkeypatch.setattr("os.name", "nt")
    assert resolve_editor_command(None, environ={}) == ["notepad"]


def test_edit_writes_text_and_reads_back_changes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[Path, str]] = []

    def fake_run(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        path = Path(argv[-1])
        captured.append((path, path.read_text(encoding="utf-8")))
        path.write_text("edited prompt\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.chdir(tmp_path)
    result = edit_prompt_text(
        "original\n",
        settings_command="fake-editor",
        environ={},
        run=fake_run,
    )

    assert result.text == "edited prompt", "trailing newline forced by console editors is stripped"
    assert result.changed is True
    assert captured == [(captured[0][0], "original\n")], "editor receives the current prompt"
    assert not captured[0][0].exists(), "temp file must be cleaned up"


def test_edit_reports_unchanged_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.chdir(tmp_path)
    result = edit_prompt_text("same", settings_command="fake-editor", environ={}, run=fake_run)
    assert result.changed is False
    assert result.text == "same"


def test_edit_reports_unchanged_even_with_trailing_newline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Console editors always force a trailing newline; the prompt strips it."""

    def fake_run(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        Path(argv[-1]).write_text("same\n", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.chdir(tmp_path)
    result = edit_prompt_text("same", settings_command="fake-editor", environ={}, run=fake_run)
    assert result.changed is False
    assert result.text == "same"


def test_edit_uses_platform_default_when_unconfigured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[list[str]] = []

    def fake_run(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.chdir(tmp_path)
    edit_prompt_text("text", settings_command=None, environ={}, platform="posix", run=fake_run)
    assert seen and seen[0][0] == "vi"


def test_edit_wraps_missing_editor_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_run(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError(argv[0])

    monkeypatch.chdir(tmp_path)
    with pytest.raises(EditorError, match="Could not start editor"):
        edit_prompt_text("text", settings_command="missing-editor", environ={}, run=failing_run)


def test_edit_wraps_nonzero_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_run(argv: list[str], *, check: bool) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(argv, 1)

    monkeypatch.chdir(tmp_path)
    with pytest.raises(EditorError, match="exited with status 1"):
        edit_prompt_text("text", settings_command="failing", environ={}, run=failing_run)
