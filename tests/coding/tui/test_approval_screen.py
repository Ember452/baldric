"""Tests for the approval card screen interactions."""

import pytest
from textual.app import App

from baldric.coding.rendering.themes import BALDRIC_DARK_THEME
from baldric.coding.trust.approvals import ApprovalDecision, ApprovalRequest, ApprovalRule
from baldric.coding.tui.screens.approval import ApprovalScreen

REQUEST = ApprovalRequest(
    tool_name="edit",
    target="C:/repo/hello.txt",
    preview="--- hello.txt\n+++ hello.txt\n@@ -1 +1 @@\n-hello\n+你好",
)
RULE = ApprovalRule(tool_name="edit", prefix="C:/repo/hello.txt")


class _Host(App[None]):
    """Pushes one approval screen and records its dismissal."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[object | None] = []

    def push_request(self) -> None:
        self.push_screen(
            ApprovalScreen(REQUEST, theme=BALDRIC_DARK_THEME, always_rule=RULE),
            self.results.append,
        )


@pytest.mark.anyio
async def test_y_allows_once_without_remembering() -> None:
    host = _Host()

    async with host.run_test() as pilot:
        host.push_request()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()

    assert host.results == [ApprovalDecision(approved=True, remember=False)]


@pytest.mark.anyio
async def test_a_allows_and_remembers() -> None:
    host = _Host()

    async with host.run_test() as pilot:
        host.push_request()
        await pilot.pause()
        await pilot.press("a")
        await pilot.pause()

    assert host.results == [ApprovalDecision(approved=True, remember=True)]


@pytest.mark.anyio
async def test_escape_rejects_with_the_default_reason() -> None:
    host = _Host()

    async with host.run_test() as pilot:
        host.push_request()
        await pilot.pause()
        await pilot.press("escape")
        await pilot.pause()

    assert host.results == [ApprovalDecision(approved=False, reason="Rejected by user")]


@pytest.mark.anyio
async def test_reject_reason_is_sent_back_to_the_model() -> None:
    host = _Host()

    async with host.run_test() as pilot:
        host.push_request()
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        await pilot.press(*"hello 删除文件")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

    decision = host.results[0]
    assert decision is not None
    assert decision.approved is False
    assert decision.reason == "hello 删除文件"


@pytest.mark.anyio
async def test_card_renders_preview_and_options() -> None:
    from rich.console import Console

    host = _Host()

    async with host.run_test() as pilot:
        host.push_request()
        await pilot.pause()

        from textual.widgets import Static

        card = host.screen.query_one("#approval-card", Static)
        console = Console(record=True, width=100, color_system=None)
        console.print(card.content)
        text = console.export_text()

    assert "Approval required — edit" in text
    assert "C:/repo/hello.txt" in text
    assert "[Y] allow once" in text
    assert "[A] always" in text
    assert "[N] reject" in text
    assert "你好" in text
    assert "+1 -1 lines" in text


@pytest.mark.anyio
async def test_tui_approval_gate_is_silent_in_auto_mode() -> None:
    import asyncio

    from baldric.coding.tui.app import BaldricTuiApp
    from baldric.coding.tui.config import TuiSettings
    from baldric.protocol.messages import ToolCall
    from tests.helpers.tui_helpers import FakeSession

    app = BaldricTuiApp(FakeSession(), tui_settings=TuiSettings(approval_mode="auto"))
    call = ToolCall(id="call-1", name="write", arguments={"path": "x.txt", "content": "hi"})

    async with app.run_test() as pilot:
        await pilot.pause()
        blocked, reason = await asyncio.wait_for(app.approval_gate(call), timeout=5)

    assert (blocked, reason) == (False, None)


@pytest.mark.anyio
async def test_tui_approval_gate_asks_then_allows_once() -> None:

    from baldric.coding.tui.app import BaldricTuiApp
    from baldric.coding.tui.config import TuiSettings
    from baldric.protocol.messages import ToolCall
    from tests.helpers.tui_helpers import FakeSession

    app = BaldricTuiApp(FakeSession(), tui_settings=TuiSettings(approval_mode="ask"))
    call = ToolCall(id="call-1", name="write", arguments={"path": "x.txt", "content": "hi"})

    async with app.run_test() as pilot:
        # The production hook runs inside a Textual worker; mirror that here,
        # because push_screen_wait requires the worker's message-pump context.
        worker = app.run_worker(app.approval_gate(call), exclusive=False)
        await pilot.pause()
        await pilot.pause()
        await pilot.press("y")
        await pilot.pause()
        blocked, reason = await worker.wait()

    assert (blocked, reason) == (False, None)
    # Allow-once leaves no session rule behind.
    assert app.approval_policy.rules == []


@pytest.mark.anyio
async def test_tui_approval_gate_reject_reason_blocks_the_call() -> None:

    from baldric.coding.tui.app import BaldricTuiApp
    from baldric.coding.tui.config import TuiSettings
    from baldric.protocol.messages import ToolCall
    from tests.helpers.tui_helpers import FakeSession

    app = BaldricTuiApp(FakeSession(), tui_settings=TuiSettings(approval_mode="ask"))
    call = ToolCall(id="call-1", name="write", arguments={"path": "x.txt", "content": "hi"})

    async with app.run_test() as pilot:
        worker = app.run_worker(app.approval_gate(call), exclusive=False)
        await pilot.pause()
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        await pilot.press(*"因为会覆盖数据")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        blocked, reason = await worker.wait()

    assert blocked is True
    assert reason == "因为会覆盖数据"
