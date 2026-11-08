import asyncio
from collections.abc import AsyncIterator, Mapping
from itertools import chain, repeat

import pytest

import baldric_agent.assistant_stream as assistant_stream_module
from baldric_agent import (
    AgentEvent,
    AgentMessage,
    AgentTool,
    AgentToolResult,
    AssistantMessage,
    MessageEndEvent,
    MessageUpdateEvent,
    RetryAttemptEvent,
    SimpleCancellationToken,
    TextContent,
    ToolCall,
    ToolExecutionEndEvent,
    ToolExecutionStartEvent,
    ToolExecutionUpdateEvent,
    ToolResultMessage,
    UserMessage,
)
from baldric_agent.loop import run_agent_loop
from baldric_agent.tool_calls import execute_tool_call
from baldric_ai import CancellationToken, FakeProvider
from baldric_protocol.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantRetryEvent,
    ThinkingDeltaEvent,
)
from baldric_protocol.types import JSONValue
from tests.helpers.pi_event_helpers import (
    assistant_done,
    assistant_error,
    assistant_start,
    text_delta,
    thinking_delta,
    tool_call_end,
)


async def _collect(stream: AsyncIterator[AgentEvent]) -> list[AgentEvent]:
    return [event async for event in stream]


def _tool(
    name: str,
    execute_fn,
) -> AgentTool:  # noqa: ANN001
    return AgentTool(
        name=name,
        label=name.title(),
        description=f"Run {name}.",
        parameters={"type": "object"},
        execute_fn=execute_fn,
    )


@pytest.mark.anyio
async def test_agent_loop_streams_canonical_nested_events() -> None:
    messages: list[AgentMessage] = [UserMessage(content="Say hello")]
    assistant = AssistantMessage(content="Hello", model="fake")
    provider = FakeProvider(
        [[assistant_start(), text_delta("Hel"), text_delta("lo"), assistant_done(assistant)]]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
        )
    )

    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_update",
        "message_update",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    updates = [event for event in events if isinstance(event, MessageUpdateEvent)]
    assert [event.assistant_message_event.delta for event in updates] == ["Hel", "lo"]  # type: ignore[union-attr]
    assert messages == [messages[0], assistant]


@pytest.mark.anyio
async def test_agent_loop_surfaces_provider_retries_before_the_message() -> None:
    messages: list[AgentMessage] = [UserMessage(content="Say hello")]
    assistant = AssistantMessage(content="Hello", model="fake")
    provider = FakeProvider(
        [
            [
                AssistantRetryEvent(attempt=1, max_attempts=3, delay_ms=250, message="HTTP 429"),
                assistant_start(),
                assistant_done(assistant),
            ]
        ]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
        )
    )

    assert [event.type for event in events][:3] == ["agent_start", "turn_start", "provider_retry"]
    retries = [event for event in events if isinstance(event, RetryAttemptEvent)]
    assert len(retries) == 1
    retry = retries[0]
    assert (retry.attempt, retry.max_attempts, retry.delay_ms, retry.message) == (
        1,
        3,
        250,
        "HTTP 429",
    )


@pytest.mark.anyio
async def test_agent_loop_records_only_monotonic_provider_wait_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = chain(
        [
            0,
            100_000_000,
            1_000_000_000,
            2_150_000_000,
            10_000_000_000,
            13_750_000_000,
        ],
        repeat(13_750_000_000),
    )
    monkeypatch.setattr(assistant_stream_module, "monotonic_ns", lambda: next(ticks))
    messages: list[AgentMessage] = [UserMessage(content="Say hello")]
    assistant = AssistantMessage(content="Hello", model="fake")
    assistant.usage.output = 100
    provider = FakeProvider([[assistant_start(), text_delta("Hello"), assistant_done(assistant)]])

    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
        )
    )

    assert assistant.timing is not None
    assert assistant.timing.time_to_first_output_ms == 1250
    assert assistant.timing.total_duration_ms == 5000


@pytest.mark.anyio
async def test_agent_loop_does_not_invent_ttft_without_an_output_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks = chain(
        [0, 100_000_000, 1_000_000_000, 2_000_000_000],
        repeat(2_000_000_000),
    )
    monkeypatch.setattr(assistant_stream_module, "monotonic_ns", lambda: next(ticks))
    assistant = AssistantMessage(content="Non-streamed", model="fake")
    provider = FakeProvider([[assistant_start(), assistant_done(assistant)]])

    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=[UserMessage(content="Say hello")],
            tools=[],
        )
    )

    assert assistant.timing is not None
    assert assistant.timing.time_to_first_output_ms is None
    assert assistant.timing.total_duration_ms == 1100


@pytest.mark.anyio
async def test_agent_loop_nests_thinking_events_without_losing_final_message() -> None:
    messages: list[AgentMessage] = [UserMessage(content="Think briefly")]
    assistant = AssistantMessage(content="Done", model="fake")
    provider = FakeProvider(
        [
            [
                assistant_start(),
                thinking_delta("hidden "),
                thinking_delta("reasoning"),
                text_delta("Done"),
                assistant_done(assistant),
            ]
        ]
    )

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
        )
    )

    nested = [
        event.assistant_message_event
        for event in events
        if isinstance(event, MessageUpdateEvent)
        and isinstance(event.assistant_message_event, ThinkingDeltaEvent)
    ]
    assert [event.delta for event in nested] == ["hidden ", "reasoning"]
    assert messages[-1] == assistant
    # The final provider message is the canonical persistence boundary.
    assert isinstance(messages[-1], AssistantMessage)


@pytest.mark.anyio
async def test_agent_loop_executes_tool_and_emits_tool_result_message_lifecycle() -> None:
    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        del tool_call_id, signal, on_update
        return AgentToolResult(
            content=[TextContent(text=f"contents of {arguments['path']}")],
            details={"path": arguments["path"]},
        )

    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    first = AssistantMessage(content=[TextContent(text="Reading."), tool_call], model="fake")
    final = AssistantMessage(content="Done.", model="fake")
    provider = FakeProvider(
        [
            [assistant_start(), tool_call_end(tool_call), assistant_done(first, "toolUse")],
            [assistant_start(), text_delta("Done."), assistant_done(final)],
        ]
    )
    messages: list[AgentMessage] = [UserMessage(content="Read README.md")]

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[_tool("read", execute)],
        )
    )

    result = next(message for message in messages if isinstance(message, ToolResultMessage))
    assert result.role == "toolResult"
    assert result.tool_name == "read"
    assert result.text == "contents of README.md"
    assert result.details == {"path": "README.md"}
    end = next(event for event in events if isinstance(event, ToolExecutionEndEvent))
    assert end.duration_ms is not None
    assert end.duration_ms >= 0
    result_lifecycle = [
        event.type for event in events if isinstance(event, (MessageEndEvent,)) and event.message is result
    ]
    assert result_lifecycle == ["message_end"]
    assert [event.type for event in events].count("message_start") == 3
    assert provider.calls[1][2] == messages[:3]


@pytest.mark.anyio
async def test_length_truncated_tool_calls_are_not_executed() -> None:
    executed: list[str] = []

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        executed.append(tool_call_id)
        raise AssertionError("a truncated tool call must not run")

    first_call = ToolCall(id="call-1", name="read", arguments={"path": "READ"})
    second_call = ToolCall(id="call-2", name="read", arguments={"path": "ME"})
    truncated = AssistantMessage(content=[first_call, second_call], model="fake")
    truncated.stop_reason = "length"
    final = AssistantMessage(content="Re-issued.", model="fake")
    provider = FakeProvider(
        [
            [
                assistant_start(),
                tool_call_end(first_call),
                tool_call_end(second_call),
                # Built directly: the shared helper treats any tool call as
                # toolUse, which would hide the truncation this test covers.
                AssistantDoneEvent(reason="length", message=truncated),
            ],
            [assistant_start(), text_delta("Re-issued."), assistant_done(final)],
        ]
    )
    messages: list[AgentMessage] = [UserMessage(content="Read both files")]

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[_tool("read", execute)],
        )
    )

    assert executed == []
    assert len(provider.calls) == 2
    results = [message for message in messages if isinstance(message, ToolResultMessage)]
    assert [result.tool_call_id for result in results] == ["call-1", "call-2"]
    assert all(result.is_error for result in results)
    assert all("output token limit" in result.text for result in results)
    ends = [event for event in events if isinstance(event, ToolExecutionEndEvent)]
    assert [event.tool_call_id for event in ends] == ["call-1", "call-2"]
    assert all(event.is_error for event in ends)
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_length_without_tool_calls_ends_normally() -> None:
    truncated = AssistantMessage(content="cut off", model="fake")
    truncated.stop_reason = "length"
    provider = FakeProvider(
        [
            [
                assistant_start(),
                text_delta("cut off"),
                AssistantDoneEvent(reason="length", message=truncated),
            ]
        ]
    )
    messages: list[AgentMessage] = [UserMessage(content="Say something")]

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
        )
    )

    assert len(provider.calls) == 1
    assert not any(isinstance(event, ToolExecutionEndEvent) for event in events)
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_repeated_truncated_tool_turns_stop_the_run() -> None:
    executed: list[str] = []

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        executed.append(tool_call_id)
        raise AssertionError("a truncated tool call must not run")

    streams = []
    for index in range(3):
        call = ToolCall(id=f"call-{index}", name="read", arguments={"path": "README.md"})
        truncated = AssistantMessage(content=[call], model="fake")
        truncated.stop_reason = "length"
        streams.append(
            [
                assistant_start(),
                tool_call_end(call),
                AssistantDoneEvent(reason="length", message=truncated),
            ]
        )
    provider = FakeProvider(streams)
    messages: list[AgentMessage] = [UserMessage(content="Read README.md")]

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[_tool("read", execute)],
        )
    )

    assert executed == []
    assert len(provider.calls) == 3
    assert len([message for message in messages if isinstance(message, ToolResultMessage)]) == 3
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_a_normal_tool_turn_resets_the_truncation_budget() -> None:
    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        del tool_call_id, arguments, signal, on_update
        return AgentToolResult(content=[TextContent(text="contents")])

    def truncated_stream(index: int) -> list[object]:
        call = ToolCall(id=f"cut-{index}", name="read", arguments={"path": "README.md"})
        truncated = AssistantMessage(content=[call], model="fake")
        truncated.stop_reason = "length"
        return [
            assistant_start(),
            tool_call_end(call),
            AssistantDoneEvent(reason="length", message=truncated),
        ]

    executed_call = ToolCall(id="call-run", name="read", arguments={"path": "README.md"})
    executed_message = AssistantMessage(content=[executed_call], model="fake")
    final = AssistantMessage(content="Done.", model="fake")
    provider = FakeProvider(
        [
            truncated_stream(1),
            [
                assistant_start(),
                tool_call_end(executed_call),
                assistant_done(executed_message, "toolUse"),
            ],
            truncated_stream(2),
            truncated_stream(3),
            [assistant_start(), text_delta("Done."), assistant_done(final)],
        ]
    )
    messages: list[AgentMessage] = [UserMessage(content="Read README.md")]

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[_tool("read", execute)],
        )
    )

    # Two truncations before the successful turn and two after must not reach the
    # budget of three consecutive truncated turns.
    assert len(provider.calls) == 5
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_cancel_during_a_stalled_stream_ends_as_aborted() -> None:
    signal = SimpleCancellationToken()
    streaming = asyncio.Event()

    class StallingProvider:
        def stream_response(self, **kwargs: object):
            token = kwargs["signal"]
            assert isinstance(token, SimpleCancellationToken)

            async def iterator():
                yield assistant_start()
                streaming.set()
                await token.wait_cancelled()
                yield AssistantErrorEvent(
                    reason="error",
                    error=AssistantMessage(model="fake", stop_reason="error"),
                )

            return iterator()

    async def cancel_once_streaming() -> None:
        await streaming.wait()
        signal.cancel()

    messages: list[AgentMessage] = [UserMessage(content="Say hello")]
    canceller = asyncio.create_task(cancel_once_streaming())
    events = await _collect(
        run_agent_loop(
            provider=StallingProvider(),
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
            signal=signal,
        )
    )
    await canceller

    final = messages[-1]
    assert isinstance(final, AssistantMessage)
    assert final.stop_reason == "aborted"
    assert final.error_message == "Operation aborted"
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_hook_that_stops_the_run_issues_no_further_request() -> None:
    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        raise AssertionError("a blocked call must not run")

    signal = SimpleCancellationToken()

    async def stop_run(call: ToolCall) -> tuple[bool, str | None]:
        del call
        signal.cancel()
        return True, "Stopped by hook."

    tool_call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    first = AssistantMessage(content=[tool_call], model="fake")
    unreached = AssistantMessage(content="Should not be requested.", model="fake")
    provider = FakeProvider(
        [
            [assistant_start(), tool_call_end(tool_call), assistant_done(first, "toolUse")],
            [assistant_start(), assistant_done(unreached)],
        ]
    )
    messages: list[AgentMessage] = [UserMessage(content="Read README.md")]

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[_tool("read", execute)],
            signal=signal,
            before_tool_call=stop_run,
        )
    )

    assert len(provider.calls) == 1
    blocked_end = next(event for event in events if isinstance(event, ToolExecutionEndEvent))
    assert blocked_end.is_error is True
    # A blocked call never runs, so it has no duration to report.
    assert blocked_end.duration_ms is None
    final = messages[-1]
    assert isinstance(final, AssistantMessage)
    assert final.stop_reason == "aborted"
    assert final.error_message == "Stopped by hook."
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_cancel_while_a_tool_runs_issues_no_further_request() -> None:
    signal = SimpleCancellationToken()

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal_arg: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        # Like bash when the user cancels a running command.
        signal.cancel()
        return AgentToolResult(content=[TextContent(text="Command cancelled")])

    tool_call = ToolCall(id="call-1", name="bash", arguments={"command": "sleep 60"})
    first = AssistantMessage(content=[tool_call], model="fake")
    unreached = AssistantMessage(content="Should not be requested.", model="fake")
    provider = FakeProvider(
        [
            [assistant_start(), tool_call_end(tool_call), assistant_done(first, "toolUse")],
            [assistant_start(), assistant_done(unreached)],
        ]
    )
    messages: list[AgentMessage] = [UserMessage(content="Wait a minute")]

    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[_tool("bash", execute)],
            signal=signal,
        )
    )

    assert len(provider.calls) == 1
    final = messages[-1]
    assert isinstance(final, AssistantMessage)
    assert final.stop_reason == "aborted"
    assert final.error_message == "Operation aborted"


@pytest.mark.anyio
async def test_agent_loop_honors_tool_result_terminate_without_another_turn() -> None:
    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        # A tool that finalizes the run, e.g. a "complete"/handoff tool.
        del tool_call_id, arguments, signal, on_update
        return AgentToolResult(content=[TextContent(text="finished")], terminate=True)

    tool_call = ToolCall(id="call-1", name="finish", arguments={})
    first = AssistantMessage(content=[tool_call], model="fake")
    unreached = AssistantMessage(content="Should not be requested.", model="fake")
    provider = FakeProvider(
        [
            [assistant_start(), tool_call_end(tool_call), assistant_done(first, "toolUse")],
            [assistant_start(), assistant_done(unreached)],
        ]
    )
    messages: list[AgentMessage] = [UserMessage(content="Finish the task")]

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[_tool("finish", execute)],
        )
    )

    # The tool asked to terminate, so the model is not asked for a follow-up turn.
    assert len(provider.calls) == 1
    # The tool result still reached the transcript and the run ends cleanly.
    assert any(isinstance(message, ToolResultMessage) for message in messages)
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_agent_loop_passes_call_id_signal_and_progress_to_tool() -> None:
    observed: list[tuple[str, CancellationToken | None]] = []

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        del arguments
        observed.append((tool_call_id, signal))
        assert on_update is not None
        on_update(AgentToolResult(content="working"))
        await asyncio.sleep(0)
        return AgentToolResult(content="done")

    call = ToolCall(id="call-1", name="work", arguments={})
    first = AssistantMessage(content=[call], model="fake")
    final = AssistantMessage(content="finished", model="fake")
    provider = FakeProvider(
        [
            [assistant_start(), tool_call_end(call), assistant_done(first, "toolUse")],
            [assistant_start(), assistant_done(final)],
        ]
    )
    signal = SimpleCancellationToken()

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=[UserMessage(content="work")],
            tools=[_tool("work", execute)],
            signal=signal,
        )
    )

    assert observed == [("call-1", signal)]
    updates = [event for event in events if isinstance(event, ToolExecutionUpdateEvent)]
    assert [event.partial_result.text for event in updates] == ["working"]


@pytest.mark.anyio
async def test_agent_loop_streams_tool_updates_while_the_tool_runs() -> None:
    # Regression test for issue #382: partials were buffered and only emitted
    # after the tool returned, so progress events carried no information at a
    # time a consumer could act on them.
    reported_first = asyncio.Event()
    release = asyncio.Event()

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        del tool_call_id, arguments, signal
        assert on_update is not None
        on_update(AgentToolResult(content="step 1"))
        reported_first.set()
        await release.wait()
        on_update(AgentToolResult(content="step 2"))
        return AgentToolResult(content="done")

    call = ToolCall(id="call-1", name="work", arguments={})
    events: list[AgentEvent] = []

    async def consume() -> None:
        async for event in execute_tool_call(
            call=call,
            tools={"work": _tool("work", execute)},
            signal=None,
            before_tool_call=None,
            after_tool_call=None,
        ):
            events.append(event)

    consumer = asyncio.create_task(consume())
    await reported_first.wait()
    for _ in range(10):
        if any(isinstance(event, ToolExecutionUpdateEvent) for event in events):
            break
        await asyncio.sleep(0)

    assert [event.partial_result.text for event in events if isinstance(event, ToolExecutionUpdateEvent)] == [
        "step 1"
    ]

    release.set()
    await consumer

    assert [event.partial_result.text for event in events if isinstance(event, ToolExecutionUpdateEvent)] == [
        "step 1",
        "step 2",
    ]
    end_events = [event for event in events if isinstance(event, ToolExecutionEndEvent)]
    assert [event.result.text for event in end_events] == ["done"]
    assert [event.is_error for event in end_events] == [False]


@pytest.mark.anyio
async def test_agent_loop_keeps_tool_updates_reported_before_a_failure() -> None:
    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        del tool_call_id, arguments, signal
        assert on_update is not None
        on_update(AgentToolResult(content="partial"))
        raise ValueError("kaboom")

    events = [
        event
        async for event in execute_tool_call(
            call=ToolCall(id="call-1", name="work", arguments={}),
            tools={"work": _tool("work", execute)},
            signal=None,
            before_tool_call=None,
            after_tool_call=None,
        )
    ]

    assert [event.partial_result.text for event in events if isinstance(event, ToolExecutionUpdateEvent)] == [
        "partial"
    ]
    end_events = [event for event in events if isinstance(event, ToolExecutionEndEvent)]
    assert [event.is_error for event in end_events] == [True]
    assert [event.result.text for event in end_events] == ["kaboom"]


@pytest.mark.anyio
async def test_agent_loop_records_unknown_tool_as_canonical_error_result() -> None:
    call = ToolCall(id="call-1", name="missing", arguments={})
    assistant = AssistantMessage(content=[call], model="fake")
    messages: list[AgentMessage] = [UserMessage(content="Use it")]
    provider = FakeProvider([[assistant_start(), tool_call_end(call), assistant_done(assistant, "toolUse")]])

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
            max_turns=1,
        )
    )

    end = next(event for event in events if isinstance(event, ToolExecutionEndEvent))
    assert end.is_error is True
    assert end.result.text == "Tool missing not found"
    result = next(message for message in messages if isinstance(message, ToolResultMessage))
    assert result.is_error is True
    assert result.text == "Tool missing not found"


@pytest.mark.anyio
async def test_agent_loop_converts_provider_error_to_assistant_error_message() -> None:
    messages: list[AgentMessage] = [UserMessage(content="hello")]
    provider = FakeProvider([[assistant_error("provider failed")]])

    events = await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
        )
    )

    assert [event.type for event in events] == [
        "agent_start",
        "turn_start",
        "message_start",
        "message_end",
        "turn_end",
        "agent_end",
    ]
    error = messages[-1]
    assert isinstance(error, AssistantMessage)
    assert error.stop_reason == "error"
    assert error.error_message == "provider failed"


@pytest.mark.anyio
async def test_agent_loop_excludes_empty_failed_assistant_from_next_provider_call() -> None:
    messages: list[AgentMessage] = []
    recovered = AssistantMessage(content="recovered", model="fake")
    provider = FakeProvider(
        [
            [assistant_error("provider failed")],
            [assistant_start(), assistant_done(recovered)],
        ]
    )

    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
            prompts=[UserMessage(content="hello")],
        )
    )
    failed = messages[-1]
    assert isinstance(failed, AssistantMessage)
    assert failed.stop_reason == "error"

    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
            prompts=[UserMessage(content="continue")],
        )
    )

    assert failed in messages
    replayed = provider.calls[1][2]
    assert [message.text for message in replayed] == ["hello", "continue"]
    assert failed not in replayed
    assert messages[-1] is recovered


@pytest.mark.anyio
async def test_agent_loop_repairs_malformed_tool_history_before_provider_call() -> None:
    call = ToolCall(id="call-1", name="read", arguments={"path": "README.md"})
    assistant = AssistantMessage(content=[call])
    late_user = UserMessage(content="continue")
    orphan = ToolResultMessage(tool_call_id="call-missing", tool_name="bash", content="orphan")
    recovered = AssistantMessage(content="recovered", model="fake")
    provider = FakeProvider([[assistant_start(), assistant_done(recovered)]])
    messages: list[AgentMessage] = [assistant, late_user, orphan]

    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
        )
    )

    replayed = provider.calls[0][2]
    assert replayed[0] is assistant
    repair = replayed[1]
    assert isinstance(repair, ToolResultMessage)
    assert repair.tool_call_id == "call-1"
    assert repair.is_error is True
    assert replayed[2] is late_user
    assert orphan not in replayed
    assert orphan in messages


@pytest.mark.anyio
async def test_agent_loop_injects_steering_and_follow_up_messages() -> None:
    call = ToolCall(id="call-1", name="work", arguments={})

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal=None,  # noqa: ANN001
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        del tool_call_id, arguments, signal, on_update
        return AgentToolResult(content="ok")

    first = AssistantMessage(content=[call], model="fake")
    second = AssistantMessage(content="second", model="fake")
    third = AssistantMessage(content="third", model="fake")
    provider = FakeProvider(
        [
            [assistant_start(), tool_call_end(call), assistant_done(first, "toolUse")],
            [assistant_start(), assistant_done(second)],
            [assistant_start(), assistant_done(third)],
        ]
    )
    steering = [UserMessage(content="steer")]
    follow_up = [UserMessage(content="follow up")]

    def pop(queue: list[UserMessage]) -> tuple[UserMessage, ...]:
        return (queue.pop(0),) if queue else ()

    messages: list[AgentMessage] = [UserMessage(content="start")]
    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[_tool("work", execute)],
            get_steering_messages=lambda: pop(steering),
            get_follow_up_messages=lambda: pop(follow_up),
        )
    )

    assert [message.text for message in messages if isinstance(message, UserMessage)] == [
        "start",
        "steer",
        "follow up",
    ]
    assert len(provider.calls) == 3


@pytest.mark.anyio
async def test_agent_loop_stops_with_assistant_error_after_max_turns() -> None:
    call = ToolCall(id="call-1", name="missing", arguments={})
    assistant = AssistantMessage(content=[call], model="fake")
    provider = FakeProvider([[assistant_start(), tool_call_end(call), assistant_done(assistant, "toolUse")]])
    messages: list[AgentMessage] = [UserMessage(content="loop")]

    await _collect(
        run_agent_loop(
            provider=provider,
            model="fake",
            system="You are Baldric.",
            messages=messages,
            tools=[],
            max_turns=1,
        )
    )

    error = messages[-1]
    assert isinstance(error, AssistantMessage)
    assert error.stop_reason == "error"
    assert error.error_message == "Agent stopped after max_turns=1"
    assert len(provider.calls) == 1


@pytest.mark.anyio
async def test_closing_tool_call_generator_mid_run_emits_clean_result_not_indexerror() -> None:
    """Closing the tool-call generator while the tool runs must not crash.

    Regression: ``run_tool`` appends the final ``(result, is_error)`` pair only
    after the tool returns. When the consumer closes the generator mid-run (an
    interrupted turn), ``GeneratorExit`` unwinds through ``run_tool``'s finally
    without appending, and ``execute_tool_call`` used to do ``outcome[0]`` on an
    empty list -> ``IndexError``. It must instead synthesize an interrupted
    result and emit a clean ``tool_execution_end``.
    """
    started = asyncio.Event()
    release = asyncio.Event()

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, JSONValue],
        signal: CancellationToken | None = None,
        on_update=None,  # noqa: ANN001
    ) -> AgentToolResult:
        del tool_call_id, arguments, signal
        assert on_update is not None
        on_update(AgentToolResult(content="working"))  # gives run_tool a partial to yield
        started.set()
        await release.wait()  # runs until interrupted
        return AgentToolResult(content="never reached")

    call = ToolCall(id="call-1", name="long", arguments={})
    generator = execute_tool_call(
        call=call,
        tools={"long": _tool("long", execute)},
        signal=None,
        before_tool_call=None,
        after_tool_call=None,
    )

    # event 1: tool_execution_start. event 2: tool_execution_update (tool is running).
    first = await generator.__anext__()
    assert isinstance(first, ToolExecutionStartEvent)
    second = await generator.__anext__()
    assert isinstance(second, ToolExecutionUpdateEvent)
    await asyncio.wait_for(started.wait(), timeout=1.0)

    await generator.aclose()  # interrupt mid-run; must not raise IndexError
