import asyncio
from collections.abc import Mapping

import pytest

from baldric.agent import (
    AgentEvent,
    AgentHarness,
    AgentHarnessConfig,
    AgentMessage,
    AgentTool,
    AgentToolResult,
    AssistantMessage,
    MessageEndEvent,
    MessageStartEvent,
    TextContent,
    ToolCall,
    ToolResultMessage,
    TurnStartEvent,
)
from baldric.ai import FakeProvider
from baldric.protocol.types import JSONValue
from tests.helpers.pi_event_helpers import (
    assistant_done,
    assistant_error,
    assistant_start,
    text_delta,
    tool_call_end,
)


def _texts(harness: AgentHarness) -> list[tuple[str, str]]:
    return [(message.role, getattr(message, "text", "")) for message in harness.messages]


@pytest.mark.anyio
async def test_prompt_appends_user_and_assistant_with_pi_lifecycle() -> None:
    assistant = AssistantMessage(content="Hello")
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=FakeProvider([[assistant_start(), assistant_done(assistant)]]),
            model="fake",
            system="You are Baldric.",
        )
    )

    events = [event async for event in harness.prompt("Hi")]

    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "message_start",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    starts = [event for event in events if isinstance(event, MessageStartEvent)]
    assert [event.message.role for event in starts] == ["user", "assistant"]
    assert _texts(harness) == [("user", "Hi"), ("assistant", "Hello")]


@pytest.mark.anyio
async def test_subscribers_receive_nested_message_updates_and_unsubscribe() -> None:
    assistant = AssistantMessage(content="Hello")
    provider = FakeProvider(
        [
            [assistant_start(), text_delta("Hello"), assistant_done(assistant)],
            [assistant_start(), assistant_done(assistant)],
        ]
    )
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            session_id="session-123",
        )
    )
    seen: list[str] = []
    unsubscribe = harness.subscribe(lambda event: seen.append(event.type))

    _ = [event async for event in harness.prompt("Hi")]
    unsubscribe()
    # The continuation consumes the queued follow-up as its prompt.
    harness.follow_up("Later")
    _ = [event async for event in harness.continue_()]

    assert "message_update" in seen
    assert seen[-1] == "agent_end"
    assert len(provider.calls) == 2
    assert provider.session_ids == ["session-123", "session-123"]


@pytest.mark.anyio
async def test_harness_rejects_overlap_and_drains_followups() -> None:
    first = AssistantMessage(content="First")
    second = AssistantMessage(content="Second")
    provider = FakeProvider(
        [
            [assistant_start(), assistant_done(first)],
            [assistant_start(), assistant_done(second)],
        ]
    )
    harness = AgentHarness(AgentHarnessConfig(provider=provider, model="fake", system="You are Baldric."))

    queued = False
    async for event in harness.prompt("Hi"):
        if isinstance(event, MessageStartEvent) and event.message.role == "assistant" and not queued:
            with pytest.raises(RuntimeError, match="already running"):
                harness.prompt("overlap")
            harness.follow_up("Later")
            queued = True

    assert _texts(harness) == [
        ("user", "Hi"),
        ("assistant", "First"),
        ("user", "Later"),
        ("assistant", "Second"),
    ]


@pytest.mark.anyio
async def test_convert_violation_ends_run_with_synthesized_error() -> None:
    """Hooks must not raise; a violation ends the run fail-visible.

    Pi agent.ts:542-558: the consumer still receives the complete tail
    (message_start/end, turn_end, agent_end) and the iterator finishes
    normally instead of throwing.
    """

    def convert(items: list[AgentMessage]) -> list[AgentMessage]:
        raise RuntimeError("bad hook")

    harness = AgentHarness(
        AgentHarnessConfig(
            provider=FakeProvider([[assistant_start(), assistant_done(AssistantMessage(content="Hi"))]]),
            model="fake",
            system="You are Baldric.",
            convert_to_llm=convert,
        )
    )

    events = [event async for event in harness.prompt("Hi")]

    assert [event.type for event in events][-4:] == ["message_start", "message_end", "turn_end", "agent_end"]
    failure = events[-1].messages[0]
    assert isinstance(failure, AssistantMessage)
    assert failure.stop_reason == "error"
    assert failure.error_message == "bad hook"
    # The forensics the old raise-through path provided ride with the message.
    crash = next(diagnostic for diagnostic in failure.diagnostics or [] if diagnostic.type == "agent_crash")
    assert crash.details["type"] == "RuntimeError"
    assert crash.details["message"] == "bad hook"
    assert "bad hook" in crash.details["traceback"]
    assert _texts(harness) == [("user", "Hi"), ("assistant", "")]
    assert harness.is_running is False


@pytest.mark.anyio
async def test_mid_run_crash_synthesizes_error_and_releases_the_harness() -> None:
    """A crash between turns ends the run with a synthesized failure.

    The transform arms itself once the tool-calling turn is on record; the
    second request raises before contacting the provider. The failure message
    joins history, the iterator ends normally, and the harness is reusable.
    """
    call = ToolCall(id="call-1", name="read", arguments={})
    assistant = AssistantMessage(content=[call], model="fake")
    provider = FakeProvider([[assistant_start(), tool_call_end(call), assistant_done(assistant, "toolUse")]])

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: object,
        on_update: object,
    ) -> AgentToolResult:
        return AgentToolResult(content=[TextContent(text="ok")], details={})

    armed = False

    def transform(items: list[AgentMessage]) -> list[AgentMessage]:
        if armed:
            raise RuntimeError("boom")
        return items

    async def listener(event: AgentEvent) -> None:
        nonlocal armed
        if isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage):
            armed = bool(event.message.tool_calls)

    harness = AgentHarness(
        AgentHarnessConfig(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            tools=[
                AgentTool(
                    name="read",
                    label="Read",
                    description="Run read.",
                    parameters={"type": "object"},
                    execute_fn=execute,
                )
            ],
            transform_context=transform,
        )
    )
    harness.subscribe(listener)

    events = [event async for event in harness.prompt("Hi")]

    assert [event.type for event in events][-4:] == ["message_start", "message_end", "turn_end", "agent_end"]
    failure = events[-1].messages[0]
    assert isinstance(failure, AssistantMessage)
    assert failure.error_message == "boom"
    assert _texts(harness)[-1] == ("assistant", "")
    assert len(provider.calls) == 1
    assert harness.is_running is False


@pytest.mark.anyio
async def test_config_turn_hooks_reach_the_loop() -> None:
    """AgentHarnessConfig passes the turn hooks through to run_agent_loop."""

    harness = AgentHarness(
        AgentHarnessConfig(
            provider=FakeProvider([[assistant_start(), assistant_done(AssistantMessage(content="Hi"))]]),
            model="fake",
            system="You are Baldric.",
            finish_turn=lambda turn: "end",
        )
    )

    events = [event async for event in harness.prompt("Hi")]

    assert sum(isinstance(event, TurnStartEvent) for event in events) == 1
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_run_state_observability_tracks_the_current_run() -> None:
    """The harness reduces events into pollable state (pi AgentState)."""
    call = ToolCall(id="call-1", name="read", arguments={})
    assistant = AssistantMessage(content=[call], model="fake")
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=FakeProvider(
                [
                    [
                        assistant_start(),
                        text_delta("working"),
                        tool_call_end(call),
                        assistant_done(assistant, "toolUse"),
                    ],
                    [assistant_start(), assistant_done(AssistantMessage(content="done"))],
                ]
            ),
            model="fake",
            system="You are Baldric.",
            tools=[
                AgentTool(
                    name="read",
                    label="Read",
                    description="Run read.",
                    parameters={"type": "object"},
                    execute_fn=_ok_execute,
                )
            ],
        )
    )
    observed: list[tuple[str, str | None, frozenset[str], bool]] = []

    async def listener(event: AgentEvent) -> None:
        streaming = harness.streaming_message
        observed.append(
            (
                event.type,
                type(streaming).__name__ if streaming is not None else None,
                harness.pending_tool_calls,
                harness.signal is not None,
            )
        )

    harness.subscribe(listener)
    _ = [event async for event in harness.prompt("Hi")]

    assert any(row[0] == "message_update" and row[1] == "AssistantMessage" for row in observed)
    assert all(row[1] is None for row in observed if row[0] == "message_end")
    start_rows = [row for row in observed if row[0] == "tool_execution_start"]
    assert start_rows and start_rows[0][2] == frozenset({"call-1"})
    end_rows = [row for row in observed if row[0] == "tool_execution_end"]
    assert end_rows and end_rows[0][2] == frozenset()
    assert observed and all(row[3] for row in observed)
    assert harness.streaming_message is None
    assert harness.pending_tool_calls == frozenset()
    assert harness.error_message is None
    assert harness.signal is None


@pytest.mark.anyio
async def test_error_message_observability_records_failed_turns() -> None:
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=FakeProvider([[assistant_error("provider failed")]]),
            model="fake",
            system="You are Baldric.",
        )
    )

    _ = [event async for event in harness.prompt("Hi")]

    assert harness.error_message == "provider failed"


@pytest.mark.anyio
async def test_queue_mode_is_runtime_switchable() -> None:
    """One queue mode covers both queues by design; it can switch between runs.

    Under the default one-at-a-time mode each poll - including the run's
    initial one - delivers a single queued message; after switching to "all",
    the run's initial poll drains the whole queue into the first turn.
    """
    provider = FakeProvider(
        [
            [assistant_start(), assistant_done(AssistantMessage(content="First"))],
            [assistant_start(), assistant_done(AssistantMessage(content="Second"))],
            [assistant_start(), assistant_done(AssistantMessage(content="Third"))],
        ]
    )
    harness = AgentHarness(AgentHarnessConfig(provider=provider, model="fake", system="You are Baldric."))
    harness.steer("one")
    harness.steer("two")

    _ = [event async for event in harness.prompt("go")]

    assert len(provider.calls) == 2
    assert "one" in [m.text for m in provider.calls[0][2]]
    assert "two" not in [m.text for m in provider.calls[0][2]]
    assert "two" in [m.text for m in provider.calls[1][2]]

    harness.queue_mode = "all"
    harness.steer("three")
    harness.steer("four")
    _ = [event async for event in harness.prompt("more")]

    assert len(provider.calls) == 3
    texts = [m.text for m in provider.calls[2][2]]
    assert "three" in texts and "four" in texts
    assert harness.pending_message_count == 0


async def _ok_execute(
    tool_call_id: str,
    arguments: Mapping[str, JSONValue],
    signal: object,
    on_update: object,
) -> AgentToolResult:
    return AgentToolResult(content=[TextContent(text="ok")], details={})


@pytest.mark.anyio
async def test_harness_queue_mode_all_drains_messages_together() -> None:
    first = AssistantMessage(content="First")
    second = AssistantMessage(content="Second")
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=FakeProvider(
                [
                    [assistant_start(), assistant_done(first)],
                    [assistant_start(), assistant_done(second)],
                ]
            ),
            model="fake",
            system="You are Baldric.",
            queue_mode="all",
        )
    )

    async for event in harness.prompt("Hi"):
        if (
            isinstance(event, MessageEndEvent)
            and isinstance(event.message, AssistantMessage)
            and event.message.text == "First"
        ):
            harness.follow_up("Second prompt")
            harness.follow_up("Third prompt")

    assert [text for role, text in _texts(harness) if role == "user"] == [
        "Hi",
        "Second prompt",
        "Third prompt",
    ]


@pytest.mark.anyio
async def test_harness_passes_canonical_tools_to_loop() -> None:
    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal=None,
        on_update=None,
    ) -> AgentToolResult:
        del tool_call_id, signal, on_update
        return AgentToolResult(content=str(arguments["text"]))

    tool = AgentTool(
        name="echo",
        label="Echo",
        description="Echo text.",
        parameters={"type": "object"},
        execute_fn=execute,
    )
    call = ToolCall(id="call-1", name="echo", arguments={"text": "hi"})
    first = AssistantMessage(content=[call])
    final = AssistantMessage(content="Done")
    provider = FakeProvider(
        [
            [assistant_start(), tool_call_end(call), assistant_done(first, "toolUse")],
            [assistant_start(), assistant_done(final)],
        ]
    )
    harness = AgentHarness(
        AgentHarnessConfig(provider=provider, model="fake", system="You are Baldric.", tools=[tool])
    )

    _ = [event async for event in harness.prompt("echo")]

    result = next(message for message in harness.messages if isinstance(message, ToolResultMessage))
    assert result.tool_name == "echo"
    assert result.text == "hi"
    assert provider.calls[0][3] == [tool]


def test_queue_mutators_return_canonical_snapshots() -> None:
    harness = AgentHarness(
        AgentHarnessConfig(provider=FakeProvider([]), model="fake", system="You are Baldric.")
    )

    harness.steer("First")
    second = harness.steer("Second").steering[-1]
    later = harness.follow_up("Later").follow_up[-1]
    assert harness.pop_latest_steering() == second
    assert harness.pop_latest_follow_up() == later
    assert [message.text for message in harness.queued_messages.steering] == ["First"]

    cleared = harness.clear_queues()
    assert [message.text for message in cleared.steering] == ["First"]
    assert harness.pending_message_count == 0


def _blocking_tool(tool_started: "asyncio.Event", release: "asyncio.Event") -> AgentTool:
    async def hang(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal=None,
        on_update=None,
    ) -> AgentToolResult:
        del tool_call_id, arguments, signal, on_update
        tool_started.set()
        await release.wait()
        return AgentToolResult(content="done")

    return AgentTool(
        name="hang",
        label="Hang",
        description="Block until released.",
        parameters={"type": "object"},
        execute_fn=hang,
    )


def _blocking_run_harness(tool_started: "asyncio.Event", release: "asyncio.Event") -> AgentHarness:
    call = ToolCall(id="call-1", name="hang", arguments={})
    assistant = AssistantMessage(content=[call])
    provider = FakeProvider([[assistant_start(), tool_call_end(call), assistant_done(assistant, "toolUse")]])
    return AgentHarness(
        AgentHarnessConfig(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            tools=[_blocking_tool(tool_started, release)],
        )
    )


@pytest.mark.anyio
async def test_cancelled_run_notifies_listeners_of_interrupted_tool_repair() -> None:
    # Regression: the cancelled-cleanup repair emitted no events, so
    # push-based subscribers never saw it.
    tool_started = asyncio.Event()
    release = asyncio.Event()
    harness = _blocking_run_harness(tool_started, release)
    seen: list[object] = []
    harness.subscribe(seen.append)

    async def consume() -> None:
        async for _event in harness.prompt("go"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(tool_started.wait(), timeout=5)
    harness.cancel()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    repair = harness.messages[-1]
    assert isinstance(repair, ToolResultMessage)
    assert repair.text == "Tool call interrupted by user"
    repair_ends = [
        event
        for event in seen
        if isinstance(event, MessageEndEvent) and isinstance(event.message, ToolResultMessage)
    ]
    assert [event.message.tool_call_id for event in repair_ends] == ["call-1"]


@pytest.mark.anyio
async def test_listener_error_during_teardown_does_not_mask_cancellation() -> None:
    tool_started = asyncio.Event()
    release = asyncio.Event()
    harness = _blocking_run_harness(tool_started, release)

    def explode(event: object) -> None:
        if isinstance(event, MessageEndEvent) and isinstance(event.message, ToolResultMessage):
            raise RuntimeError("listener exploded")

    harness.subscribe(explode)

    async def consume() -> None:
        async for _event in harness.prompt("go"):
            pass

    task = asyncio.create_task(consume())
    await asyncio.wait_for(tool_started.wait(), timeout=5)
    harness.cancel()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert isinstance(harness.messages[-1], ToolResultMessage)


def test_harness_repairs_interrupted_tool_calls() -> None:
    call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    harness = AgentHarness(
        AgentHarnessConfig(provider=FakeProvider([]), model="fake", system="You are Baldric."),
        messages=[AssistantMessage(content=[TextContent(text="Reading"), call])],
    )

    assert harness.append_interrupted_tool_results() == 1
    repair = harness.messages[-1]
    assert isinstance(repair, ToolResultMessage)
    assert repair.is_error is True
    assert repair.text == "Tool call interrupted by user"


@pytest.mark.anyio
async def test_entry_path_repair_is_pushed_to_listeners() -> None:
    # A transcript can reach prompt()/continue_() with a dangling tool call
    # (for example after a persist failure killed the previous run). The
    # synthetic repair must flow through events so push persistence sees it.
    call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    harness = AgentHarness(
        AgentHarnessConfig(
            provider=FakeProvider(
                [[assistant_start(), assistant_done(AssistantMessage(content="Recovered."))]]
            ),
            model="fake",
            system="You are Baldric.",
        ),
        messages=[AssistantMessage(content=[call])],
    )
    seen: list[object] = []
    harness.subscribe(seen.append)

    events = [event async for event in harness.prompt("continue")]

    assert [event.type for event in events[:4]] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
    ]
    repair = next(message for message in harness.messages if isinstance(message, ToolResultMessage))
    assert repair.tool_call_id == "call-1"
    listener_ends = [
        event.message.tool_call_id
        for event in seen
        if isinstance(event, MessageEndEvent) and isinstance(event.message, ToolResultMessage)
    ]
    assert listener_ends == ["call-1"]
    consumer_ends = [
        event.message.tool_call_id
        for event in events
        if isinstance(event, MessageEndEvent) and isinstance(event.message, ToolResultMessage)
    ]
    assert consumer_ends == ["call-1"]
