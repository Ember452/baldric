"""Lifecycle hooks (plan Task F): user_bash, model_select, set_model /
set_thinking_level, and the thinking_level_select alias.

Runtime-level tests pin the API surface (set_model/set_thinking_level delegate
and notify); session-level tests prove the real paths: a ``!`` command is
answered by an extension without touching the shell, and a thinking-level change
reaches a handler subscribed with Pi's event name.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric.runtime.platform.api import ExtensionAPI, UserBashEvent
from baldric.runtime.platform.builtin_registry import BuiltInExtension
from baldric.runtime.platform.runtime import ExtensionRuntime
from baldric.runtime.session.session import CodingSession, CodingSessionConfig
from baldric.runtime.session.storage import JsonlSessionStorage
from tests.runtime.extensions.test_extensions import _paths

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class _FakeSession:
    """Minimal BoundSession stub for runtime-level delegation tests."""

    cwd = Path("/w")
    provider_name = "fake"
    session_id = None
    session_name = None
    thinking_level = "medium"

    def __init__(self) -> None:
        self.model = "m1"
        self.selected: list[str | None] = []
        self.thinking_requests: list[str] = []

    def set_model(self, model: str) -> None:
        self.model = model

    async def notify_model_selected(self, previous_model: str | None) -> None:
        self.selected.append(previous_model)

    async def set_thinking_level(self, level: str) -> str:
        self.thinking_requests.append(level)
        return "high"


def _runtime(tmp_path: Path, setup) -> ExtensionRuntime:
    runtime = ExtensionRuntime(built_in_extensions=(BuiltInExtension(name="ext", setup=setup),))
    runtime.load(_paths(tmp_path), include_resource_dirs=False)
    return runtime


async def test_set_model_delegates_and_notifies(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, lambda api: None)
    fake = _FakeSession()
    runtime.bind(fake)

    await runtime.set_model("m2")

    assert fake.model == "m2"
    assert fake.selected == ["m1"]


async def test_set_model_is_a_noop_when_unchanged(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, lambda api: None)
    fake = _FakeSession()
    runtime.bind(fake)

    await runtime.set_model("m1")

    assert fake.selected == []


async def test_set_thinking_level_api_delegates(tmp_path: Path) -> None:
    captured: list[ExtensionAPI] = []

    def setup(api: ExtensionAPI) -> None:
        captured.append(api)

    runtime = _runtime(tmp_path, setup)
    fake = _FakeSession()
    runtime.bind(fake)

    applied = await captured[0].set_thinking_level("high")

    assert applied == "high"
    assert fake.thinking_requests == ["high"]


async def test_run_user_bash_returns_first_result_and_defers_none(tmp_path: Path) -> None:
    def setup(api: ExtensionAPI) -> None:
        from baldric.runtime.platform.api import UserBashResult

        def answer(event: UserBashEvent, ctx) -> UserBashResult:
            return UserBashResult(output=f"remote:{event.command}", exit_code=0)

        api.on("user_bash", lambda event, ctx: None)
        api.on("user_bash", answer)

    runtime = _runtime(tmp_path, setup)

    result = await runtime.run_user_bash(UserBashEvent(command="ls", cwd=Path("/w")))

    assert result is not None
    assert result.output == "remote:ls"
    assert result.exit_code == 0


async def test_no_user_bash_handler_returns_none(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path, lambda api: None)
    assert await runtime.run_user_bash(UserBashEvent(command="ls", cwd=Path("/w"))) is None


async def test_notify_model_selected_reaches_extension_and_frontend(tmp_path: Path) -> None:
    seen = tmp_path / "model.txt"
    extension_dir = _write_hook_extension(
        tmp_path,
        f"""
from baldric.runtime.platform import ExtensionAPI

SEEN = {str(seen)!r}


def setup(api: ExtensionAPI) -> None:
    def note(event, ctx):
        with open(SEEN, "a", encoding="utf-8") as handle:
            handle.write(event.model + "|" + str(event.previous_model) + "\\n")

    api.on("model_select", note)
""",
    )
    session = await _open_session(tmp_path, extension_dir)
    try:
        await session.notify_model_selected("previous-model")

        assert seen.read_text(encoding="utf-8").strip() == "fake|previous-model"
        drained = session.drain_frontend_events()
        assert any(
            getattr(event, "type", None) == "model_select"
            and getattr(event, "previous_model", None) == "previous-model"
            for event in drained
        )
    finally:
        await session.aclose()


def _write_hook_extension(tmp_path: Path, body: str) -> Path:
    directory = tmp_path / "hook-ext"
    directory.mkdir()
    (directory / "extension.py").write_text(body, encoding="utf-8")
    return directory


async def _open_session(tmp_path: Path, extension_dir: Path) -> CodingSession:
    return await CodingSession.load(
        CodingSessionConfig(
            provider=_NullProvider(),
            model="fake",
            system="You are Baldric.",
            storage=JsonlSessionStorage(tmp_path / "session.jsonl"),
            cwd=tmp_path,
            extension_paths=(extension_dir,),
        )
    )


class _NullProvider:
    """A provider that is never called by these tests."""

    def stream_response(self, **kwargs):
        raise AssertionError("provider must not be called")


async def test_user_bash_extension_answers_without_running_the_shell(tmp_path: Path) -> None:
    seen = tmp_path / "seen.txt"
    extension_dir = _write_hook_extension(
        tmp_path,
        f"""
from baldric.runtime.platform import ExtensionAPI
from baldric.runtime.platform.api import UserBashResult

SEEN = {str(seen)!r}


def setup(api: ExtensionAPI) -> None:
    def answer(event, ctx):
        with open(SEEN, "a", encoding="utf-8") as handle:
            handle.write(event.command + "|" + str(event.exclude_from_context) + "\\n")
        return UserBashResult(output="remote-output", exit_code=0)

    api.on("user_bash", answer)
""",
    )
    session = await _open_session(tmp_path, extension_dir)
    try:
        result = await session.run_terminal_command("echo local-should-not-run", add_to_context=False)

        assert result.output == "remote-output"
        assert result.exit_code == 0
        assert result.ok is True
        assert seen.read_text(encoding="utf-8").strip() == "echo local-should-not-run|True"
    finally:
        await session.aclose()


async def test_thinking_level_select_alias_receives_previous_level(tmp_path: Path) -> None:
    seen = tmp_path / "thinking.txt"
    extension_dir = _write_hook_extension(
        tmp_path,
        f"""
from baldric.runtime.platform import ExtensionAPI

SEEN = {str(seen)!r}


def setup(api: ExtensionAPI) -> None:
    def note(event, ctx):
        with open(SEEN, "a", encoding="utf-8") as handle:
            handle.write(event.level + "|" + str(event.previous_level) + "\\n")

    # Pi's event name; the runtime aliases it onto thinking_level_changed.
    api.on("thinking_level_select", note)
""",
    )
    session = await _open_session(tmp_path, extension_dir)
    try:
        await session.set_thinking_level("high")

        assert seen.read_text(encoding="utf-8").strip() == "high|medium"
    finally:
        await session.aclose()
