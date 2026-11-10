"""Integration tests for the external-editor prompt action."""

from __future__ import annotations

from typing import Any

import pytest

from baldric.runtime.tui.app import BaldricTuiApp
from baldric.runtime.tui.editor import EditorError, EditorResult
from baldric.runtime.tui.widgets import PromptInput
from tests.helpers.tui_helpers import FakeSession


class _NotifyRecorder:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    def __call__(self, message: str, *, severity: str = "information", **_: Any) -> None:
        self.messages.append((severity, message))


def _prompt(app: BaldricTuiApp) -> PromptInput:
    return app.query_one("#prompt", PromptInput)


def _patch_editor_result(
    monkeypatch: pytest.MonkeyPatch,
    result: EditorResult,
) -> None:
    async def fake_run_external_editor(
        app: Any, text: str, *, settings_command: str | None = None
    ) -> EditorResult:
        del app, text, settings_command
        return result

    monkeypatch.setattr(
        "baldric.runtime.tui.app.run_external_editor",
        fake_run_external_editor,
    )


def _patch_editor_error(
    monkeypatch: pytest.MonkeyPatch,
    error: BaseException,
) -> None:
    async def fake_run_external_editor(
        app: Any, text: str, *, settings_command: str | None = None
    ) -> EditorResult:
        del app, text, settings_command
        raise error

    monkeypatch.setattr(
        "baldric.runtime.tui.app.run_external_editor",
        fake_run_external_editor,
    )


@pytest.mark.anyio
async def test_external_editor_replaces_prompt_text(monkeypatch: pytest.MonkeyPatch) -> None:
    app = BaldricTuiApp(FakeSession())
    recorder = _NotifyRecorder()
    monkeypatch.setattr(app, "_notify", recorder)
    _patch_editor_result(monkeypatch, EditorResult(text="edited from editor", changed=True))

    async with app.run_test() as pilot:
        prompt = _prompt(app)
        prompt.text = "original prompt"
        await pilot.press("ctrl+e")
        await pilot.pause()

    assert prompt.text == "edited from editor"
    assert prompt.cursor_position == len("edited from editor")
    assert ("information", "Prompt updated in external editor") in recorder.messages


@pytest.mark.anyio
async def test_external_editor_keeps_text_when_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    app = BaldricTuiApp(FakeSession())
    recorder = _NotifyRecorder()
    monkeypatch.setattr(app, "_notify", recorder)
    _patch_editor_result(monkeypatch, EditorResult(text="original prompt", changed=False))

    async with app.run_test() as pilot:
        prompt = _prompt(app)
        prompt.text = "original prompt"
        await pilot.press("ctrl+e")
        await pilot.pause()

    assert prompt.text == "original prompt"
    assert recorder.messages == []


@pytest.mark.anyio
async def test_external_editor_notifies_on_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    app = BaldricTuiApp(FakeSession())
    recorder = _NotifyRecorder()
    monkeypatch.setattr(app, "_notify", recorder)
    _patch_editor_error(monkeypatch, EditorError("Could not start editor 'vi': exec failed"))

    async with app.run_test() as pilot:
        prompt = _prompt(app)
        prompt.text = "keep me"
        await pilot.press("ctrl+e")
        await pilot.pause()

    assert prompt.text == "keep me"
    assert recorder.messages and recorder.messages[0][0] == "error"
    assert "Could not start editor" in recorder.messages[0][1]


@pytest.mark.anyio
async def test_external_editor_failure_keeps_text(monkeypatch: pytest.MonkeyPatch) -> None:
    app = BaldricTuiApp(FakeSession())
    recorder = _NotifyRecorder()
    monkeypatch.setattr(app, "_notify", recorder)
    _patch_editor_error(monkeypatch, EditorError("editor crashed"))

    async with app.run_test() as pilot:
        prompt = _prompt(app)
        prompt.text = "keep me"
        await pilot.press("ctrl+e")
        await pilot.pause()

    assert prompt.text == "keep me"
    assert recorder.messages and recorder.messages[0][0] == "error"


@pytest.mark.anyio
async def test_external_editor_reenables_input_after_run(monkeypatch: pytest.MonkeyPatch) -> None:
    app = BaldricTuiApp(FakeSession())
    _patch_editor_result(monkeypatch, EditorResult(text="done", changed=True))

    async with app.run_test() as pilot:
        prompt = _prompt(app)
        prompt.read_only = False
        await pilot.press("ctrl+e")
        await pilot.pause()
        assert prompt.read_only is False
