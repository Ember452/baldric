"""Hook-composition contract guard (dev-notes/architecture/hook-composition.md).

Pins the two composition rules the runtime already implements — deterministic
registration order and per-handler error isolation — so a later refactor (the
provider/session-structure hooks of plan Tasks A/B) cannot silently regress them.

It does not test rules 3 (chained vs in-place) and 4 (termination), which are
forward contract commitments for the planned seams; those get their own tests
when the seams land.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric.runtime.events import ThinkingLevelChangedEvent
from baldric.runtime.platform.api import ExtensionAPI
from baldric.runtime.platform.builtin_registry import BuiltInExtension
from baldric.runtime.platform.runtime import ExtensionRuntime
from tests.runtime.extensions.test_extensions import _paths

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _built_in(name: str, setup) -> BuiltInExtension:
    return BuiltInExtension(name=name, setup=setup)


async def test_handlers_run_in_registration_order(tmp_path: Path) -> None:
    """Rule 1: handlers run in deterministic registration (load) order."""
    calls: list[str] = []

    def setup_first(baldric: ExtensionAPI) -> None:
        baldric.on("thinking_level_changed", lambda event, ctx: calls.append("first"))

    def setup_second(baldric: ExtensionAPI) -> None:
        baldric.on("thinking_level_changed", lambda event, ctx: calls.append("second"))

    runtime = ExtensionRuntime(
        built_in_extensions=(_built_in("first", setup_first), _built_in("second", setup_second))
    )
    runtime.load(_paths(tmp_path), include_resource_dirs=False)

    await runtime.emit_event(ThinkingLevelChangedEvent(level="high"))

    assert calls == ["first", "second"]


async def test_one_handler_raising_is_isolated_and_recorded(tmp_path: Path) -> None:
    """Rule 2: a raising handler is skipped, later handlers still run, failure recorded."""
    calls: list[str] = []

    def setup_raiser(baldric: ExtensionAPI) -> None:
        def boom(event, ctx):
            calls.append("raiser")
            raise RuntimeError("kaboom")

        baldric.on("thinking_level_changed", boom)

    def setup_after(baldric: ExtensionAPI) -> None:
        baldric.on("thinking_level_changed", lambda event, ctx: calls.append("after"))

    runtime = ExtensionRuntime(
        built_in_extensions=(_built_in("raiser", setup_raiser), _built_in("after", setup_after))
    )
    runtime.load(_paths(tmp_path), include_resource_dirs=False)

    # Must not raise out of emit_event.
    await runtime.emit_event(ThinkingLevelChangedEvent(level="low"))

    assert calls == ["raiser", "after"]
    failures = [d for d in runtime.diagnostics if "kaboom" in d.message]
    assert len(failures) == 1
    assert failures[0].name == "raiser"
