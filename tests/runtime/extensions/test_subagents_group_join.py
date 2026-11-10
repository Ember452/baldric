"""Tests for background-notification group joining.

The timer policy is asserted by injecting a fake event loop that records
`call_later` delays, and the timeout path is driven by calling the timer
callback directly. Nothing here waits on a real clock, so the 30s and 15s
windows are pinned exactly and the tests cannot rotate flaky.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from baldric.runtime.extensions.builtins.subagents import group_join as group_join_module
from baldric.runtime.extensions.builtins.subagents.group_join import (
    DEFAULT_TIMEOUT,
    STRAGGLER_TIMEOUT,
    GroupJoinManager,
)

pytestmark = pytest.mark.anyio


@dataclass
class FakeRun:
    agent_id: str
    result_consumed: bool = False


@dataclass
class FakeTimer:
    delay: float
    callback: object
    args: tuple[object, ...]
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


@dataclass
class FakeLoop:
    timers: list[FakeTimer] = field(default_factory=list)

    def call_later(self, delay: float, callback: object, *args: object) -> FakeTimer:
        timer = FakeTimer(delay, callback, args)
        self.timers.append(timer)
        return timer

    def arm_delays(self) -> list[float]:
        return [timer.delay for timer in self.timers]

    def fire_next(self) -> FakeTimer:
        pending = [timer for timer in self.timers if not timer.cancelled]
        if not pending:
            raise AssertionError("no armed window to fire")
        timer = pending[0]
        timer.cancelled = True
        assert callable(timer.callback)
        timer.callback(*timer.args)  # type: ignore[operator]
        return timer


@dataclass
class Delivery:
    runs: list[FakeRun]
    partial: bool


def _manager(monkeypatch: pytest.MonkeyPatch, loop: FakeLoop) -> tuple[GroupJoinManager, list[Delivery]]:
    deliveries: list[Delivery] = []

    def deliver(runs: list[FakeRun], partial: bool) -> None:
        deliveries.append(Delivery(runs, partial))

    # Replace the module's asyncio binding rather than mutating stdlib asyncio,
    # so the patch cannot reach another test in the same process.
    monkeypatch.setattr(group_join_module, "asyncio", SimpleNamespace(get_running_loop=lambda: loop))
    return GroupJoinManager(deliver), deliveries


async def test_window_starts_at_the_first_completion_with_the_default_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = FakeLoop()
    manager, _deliveries = _manager(monkeypatch, loop)
    manager.register_group("b1", ["a1", "a2", "a3"])

    manager.on_agent_complete(FakeRun("a1"))
    manager.on_agent_complete(FakeRun("a2"))

    assert loop.arm_delays() == [DEFAULT_TIMEOUT], "registration arms nothing"


async def test_straggler_window_is_the_shorter_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = FakeLoop()
    manager, deliveries = _manager(monkeypatch, loop)
    manager.register_group("b1", ["a1", "a2", "a3"])
    manager.on_agent_complete(FakeRun("a1"))
    loop.fire_next()  # a1 partial-delivered, group now holds a2 + a3

    assert deliveries[0].partial is True
    manager.on_agent_complete(FakeRun("a2"))

    assert loop.arm_delays() == [DEFAULT_TIMEOUT, STRAGGLER_TIMEOUT]


async def test_timeout_is_silent_when_the_completed_member_was_consumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loop = FakeLoop()
    manager, deliveries = _manager(monkeypatch, loop)
    manager.register_group("b1", ["a1", "a2"])
    # a1 is unconsumed while the window is armed, then gets consumed before the
    # timeout fires: nothing is left to announce, and the straggler must survive.
    first = FakeRun("a1")
    manager.on_agent_complete(first)
    first.result_consumed = True
    deliveries.clear()

    loop.fire_next()

    assert deliveries == []
    assert manager.on_agent_complete(FakeRun("a2")) == "delivered"
    assert [[run.agent_id for run in item.runs] for item in deliveries] == [["a2"]]


async def test_delivery_cancels_the_pending_window(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = FakeLoop()
    manager, _deliveries = _manager(monkeypatch, loop)
    manager.register_group("b1", ["a1", "a2"])
    manager.on_agent_complete(FakeRun("a1"))

    manager.on_agent_complete(FakeRun("a2"))

    assert loop.timers[0].cancelled is True


async def test_delivered_agents_are_forgotten(monkeypatch: pytest.MonkeyPatch) -> None:
    """A late repeat of a delivered run must not notify the batch twice."""
    loop = FakeLoop()
    manager, deliveries = _manager(monkeypatch, loop)
    manager.register_group("b1", ["a1", "a2"])
    manager.on_agent_complete(FakeRun("a1"))

    manager.on_agent_complete(FakeRun("a2"))
    assert len(deliveries) == 1

    assert manager.on_agent_complete(FakeRun("a2")) == "pass"
    assert len(deliveries) == 1


async def test_cancel_all_cancels_timers_and_forgets_groups(monkeypatch: pytest.MonkeyPatch) -> None:
    loop = FakeLoop()
    manager, deliveries = _manager(monkeypatch, loop)
    manager.register_group("b1", ["a1", "a2"])
    manager.on_agent_complete(FakeRun("a1"))

    manager.cancel_all()

    assert loop.timers[0].cancelled is True
    assert manager.on_agent_complete(FakeRun("a1")) == "pass"
    assert deliveries == []
