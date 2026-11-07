"""Shared fakes/helpers for baldric-subagents extension tests.

Kept at ``tests/`` root so sibling test modules can import it under pytest's
rootdir import mode without ``tests`` being a package.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

from baldric_agent.messages import AssistantMessage
from baldric_ai import AssistantDoneEvent, AssistantStartEvent
from baldric_coding import BaldricResourcePaths
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.extensions import ExtensionRuntime

EXTENSION_DIR = (
    Path(__file__).resolve().parents[2] / "src" / "baldric_coding" / "extensions" / "builtins" / "subagents"
)

__all__ = [
    "BlockingProvider",
    "EXTENSION_DIR",
    "RecordingSession",
    "ScriptedUi",
    "_agent_tool",
    "_bpaths",
    "_extension_module",
    "_load_runtime",
    "_patch_provider_factory",
    "_patch_provider_sequence",
    "_patch_provider_settings",
    "_paths",
    "_runtime_paths",
    "_submodule",
    "_text_stream",
    "_wait_for",
]


def _bpaths(home):  # noqa: ANN001, ANN202 - test helper
    """BaldricPaths for a directory that stands in for the user home."""
    return BaldricPaths(home=home / ".baldric", agents_home=home / "agents")


def _paths(tmp_path: Path) -> BaldricResourcePaths:
    return BaldricResourcePaths(
        root=tmp_path / "home-baldric",
        cwd=tmp_path / "project",
        agents_root=tmp_path / "home-agents",
    )


def _runtime_paths(tmp_path: Path) -> BaldricPaths:
    """The paths object the runtime derives from `_paths(tmp_path)`.

    Locations come from the injected paths rather than `Path.home()`, so a test
    that predicts where the capability wrote must use this same pair.
    """
    return BaldricPaths(home=tmp_path / "home-baldric", agents_home=tmp_path / "home-agents")


class RecordingSession:
    """Minimal BoundSession implementation for runtime tests."""

    def __init__(self, tmp_path: Path, *, running: bool = False) -> None:
        self.cwd = tmp_path
        self.model = "fake"
        self.provider_name = "fake"
        # Deliberately not the level a hardcoded default would have picked, so a
        # child continuing at the parent's level is observable, not coincidental.
        self.thinking_level = "high"
        self.session_id = "session-1"
        self.system_prompt = "You are Baldric."
        # Defaults match a plain session so sibling tests are unaffected; the
        # inheritance test overrides these with a non-default, platform-valid
        # value to prove forwarding.
        self.shell = "auto"
        self.shell_command_prefix: str | None = None
        self.is_running = running
        # The child session inherits the parent's approval gate through the
        # context (ExtensionContext.before_tool_call); a None here is the
        # "approval mode off" case, which is what these suites exercise.
        self.before_tool_call = None
        # The trust gate reads this through the context; these tests place agent
        # definitions and settings in the project directory, so the stand-in
        # models an approved project (api.py:1000 reads `.trusted`).
        self.project_trust_resolution = SimpleNamespace(trusted=True)
        self.steered: list[str] = []
        self.followed_up: list[str] = []
        self.custom_entries: list[tuple[str, dict[str, object]]] = []
        self.messages: list[object] = []
        self.followed_up_custom: list[tuple[str | None, dict[str, object] | None]] = []

    def queue_steering_message(
        self,
        content: str,
        *,
        custom_type: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        del custom_type, details
        self.steered.append(content)

    def queue_follow_up_message(
        self,
        content: str,
        *,
        custom_type: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self.followed_up.append(content)
        self.followed_up_custom.append((custom_type, details))

    async def append_custom_entry(self, namespace: str, data: dict[str, object]) -> None:
        self.custom_entries.append((namespace, data))


def _load_runtime(tmp_path: Path) -> ExtensionRuntime:
    # These suites load the capability from its source directory through
    # ``extra_paths``, so the built-in declaration has to stay out of the way:
    # loading both would register the tools twice and the first registration
    # would win, leaving patches on the loaded copy without effect.
    runtime = ExtensionRuntime(built_in_extensions=())
    runtime.load(
        _paths(tmp_path),
        extra_paths=(EXTENSION_DIR,),
        include_resource_dirs=False,
    )
    return runtime


def _extension_module() -> object:
    candidates = [
        module
        for module_name, module in sys.modules.items()
        if module_name.startswith("baldric_extension_subagents") and "." not in module_name
    ]
    assert candidates, "extension module not loaded"
    return candidates[-1]


def _submodule(name: str) -> object:
    top = _extension_module()
    return sys.modules[f"{top.__name__}.{name}"]  # type: ignore[attr-defined]


def _agent_tool(runtime: ExtensionRuntime):  # noqa: ANN202
    return next(tool for tool in runtime.extension_tools if tool.name == "agent")


def _text_stream(text: str) -> list[object]:
    return [
        AssistantStartEvent(partial=AssistantMessage(model="fake")),
        AssistantDoneEvent(reason="stop", message=AssistantMessage(content=text)),
    ]


class BlockingProvider:
    """A provider whose single text response waits on an event before yielding."""

    def __init__(self, release: asyncio.Event, text: str) -> None:
        self._release = release
        self._text = text
        self.calls: list[object] = []

    def stream_response(  # noqa: ANN001, ANN202
        self, *, model, system, messages, tools, signal=None, session_id=None
    ):
        self.calls.append(list(messages))

        async def iterator():  # noqa: ANN202
            await self._release.wait()
            yield AssistantStartEvent(partial=AssistantMessage(model="fake"))
            yield AssistantDoneEvent(reason="stop", message=AssistantMessage(content=self._text))

        return iterator()


def _patch_provider_settings(module: object) -> None:
    module.load_provider_settings = lambda: None  # type: ignore[attr-defined]
    module.resolve_provider_selection = (  # type: ignore[attr-defined]
        lambda settings, provider_name=None, model=None: SimpleNamespace(
            provider=SimpleNamespace(name="fake"), model="fake"
        )
    )


def _patch_provider_factory(module: object, provider: object) -> None:
    _patch_provider_settings(module)
    module.create_model_provider = (  # type: ignore[attr-defined]
        lambda provider_arg, model, thinking_level: provider
    )


def _patch_provider_sequence(module: object, providers: list[object]) -> None:
    _patch_provider_settings(module)
    it = iter(providers)
    module.create_model_provider = (  # type: ignore[attr-defined]
        lambda provider_arg, model, thinking_level: next(it)
    )


async def _wait_for(condition, *, tries: int = 500) -> None:  # noqa: ANN001
    for _ in range(tries):
        if condition():
            return
        await asyncio.sleep(0.01)


class ScriptedUi:
    """Scripted DialogUi fake for menu tests."""

    def __init__(self, selects, confirms=(), inputs=()) -> None:  # noqa: ANN001
        self.selects = list(selects)
        self.confirms = list(confirms)
        self.inputs = list(inputs)
        self.select_calls: list[tuple[str, tuple[str, ...]]] = []
        self.notifications: list[str] = []

    @property
    def has_ui(self) -> bool:
        return True

    def notify(self, message: str, level: str = "info") -> None:
        self.notifications.append(message)

    async def select(self, title, options, *, timeout=None):  # noqa: ANN001, ANN202
        self.select_calls.append((title, tuple(options)))
        answer = self.selects.pop(0)
        return answer(options) if callable(answer) else answer

    async def confirm(self, title, message, *, timeout=None):  # noqa: ANN001, ANN202
        return self.confirms.pop(0)

    async def input(self, title, placeholder="", *, timeout=None):  # noqa: ANN001, ANN202
        return self.inputs.pop(0)
