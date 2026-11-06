"""Provider rejection of image tools is recoverable without changing durable history.

Ported from Tau's image-tool-error-recovery regression suite (issue #36).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

from baldric_agent import (
    AgentEvent,
    AgentMessage,
    AssistantMessage,
    ImageContent,
    SimpleCancellationToken,
    TextContent,
    ToolCall,
    ToolResultMessage,
    UserMessage,
)
from baldric_agent.loop import _provider_context, run_agent_loop
from baldric_ai import CancellationToken, FakeProvider
from tests.helpers.pi_event_helpers import assistant_done, assistant_error


def _image_history() -> list[AgentMessage]:
    return [
        UserMessage(content="Read image.png"),
        AssistantMessage(content=[ToolCall(id="image", name="read", arguments={})]),
        ToolResultMessage(
            tool_call_id="image",
            tool_name="read",
            content=[
                TextContent(text="Read image.png"),
                ImageContent(data="AA==", mime_type="image/png"),
            ],
            details={"path": "image.png"},
        ),
    ]


def _tool(execute: Any) -> Any:
    from baldric_agent.tools import AgentTool

    return AgentTool(
        name="read",
        label="Read",
        description="take a screenshot",
        parameters={"type": "object"},
        execute_fn=execute,
    )


async def _run(
    provider: FakeProvider,
    messages: list[AgentMessage],
    *,
    signal: CancellationToken | None = None,
    max_turns: int | None = None,
) -> list[AgentEvent]:
    return [
        event
        async for event in run_agent_loop(
            provider=provider,
            model="fake",
            system="",
            messages=messages,
            tools=[],
            signal=signal,
            max_turns=max_turns,
        )
    ]


@pytest.mark.anyio
async def test_image_rejection_reaches_model_as_tool_error_and_preserves_history() -> None:
    messages = _image_history()
    original = messages[2].model_copy(deep=True)
    provider = FakeProvider(
        [
            [assistant_error("image exceeds maximum size")],
            [assistant_done(AssistantMessage(content="Use a thumbnail."))],
        ]
    )

    events = await _run(provider, messages)

    assert len(provider.calls) == 2
    recovered = provider.calls[1][2][2]
    assert isinstance(recovered, ToolResultMessage)
    assert recovered.tool_call_id == "image"
    assert recovered.tool_name == "read"
    assert recovered.is_error
    assert recovered.details == {"path": "image.png"}
    assert "image exceeds maximum size" in recovered.text
    assert all(isinstance(block, TextContent) for block in recovered.content)
    assert messages[2] == original
    assert messages[-1].text == "Use a thumbnail."
    assert [event.type for event in events].count("agent_end") == 1
    assert [event.type for event in events].count("turn_end") == 2
    # JSONL replay must reconstruct the same safe context, without in-place edits.
    restored = [type(message).model_validate_json(message.model_dump_json()) for message in messages]
    assert _provider_context(restored) == _provider_context(messages)
    assert _provider_context(restored)[2] == recovered


@pytest.mark.anyio
async def test_image_recovery_stops_on_third_consecutive_error() -> None:
    messages = _image_history()
    provider = FakeProvider([[assistant_error(f"API unavailable {i}")] for i in range(4)])

    events = await _run(provider, messages)

    assert len(provider.calls) == 3
    assert messages[-1].error_message == "API unavailable 2"
    assert "API unavailable 1" in provider.calls[2][2][2].text
    assert events[-1].type == "agent_end"
    assert [event.type for event in events].count("turn_start") == 3


@pytest.mark.anyio
async def test_success_resets_error_streak_and_tools_are_not_rerun() -> None:
    executions = 0

    async def execute(
        tool_call_id: str,
        arguments: Mapping[str, Any],
        signal: Any = None,
        on_update: Any = None,
    ) -> Any:
        nonlocal executions
        executions += 1
        from baldric_agent.tools import AgentToolResult

        return AgentToolResult(content=[ImageContent(data="AA==", mime_type="image/png")])

    second_call = AssistantMessage(content=[ToolCall(id="second", name="read", arguments={})])
    provider = FakeProvider(
        [
            [assistant_error("first image rejected")],
            [assistant_error("still unavailable")],
            [assistant_done(second_call)],
            [assistant_error("second image rejected")],
            [assistant_error("temporarily unavailable")],
            [assistant_done(AssistantMessage(content="Done"))],
        ]
    )
    messages = _image_history()

    events = [
        event
        async for event in run_agent_loop(
            provider=provider,
            model="fake",
            system="",
            messages=messages,
            tools=[_tool(execute)],
        )
    ]

    # The new tool call executes exactly once; recovery replays never
    # re-execute side-effecting tools.
    assert executions == 1
    assert len(provider.calls) == 6
    assert messages[-1].text == "Done"
    assert events[-1].type == "agent_end"


@pytest.mark.anyio
async def test_image_recovery_respects_cancellation() -> None:
    signal = SimpleCancellationToken()
    messages = _image_history()
    provider = FakeProvider(
        [
            [assistant_error("image exceeds maximum size")],
            [assistant_done(AssistantMessage(content="Use a thumbnail."))],
        ]
    )
    signal.cancel()
    events = await _run(provider, messages, signal=signal)

    assert events[-1].type == "agent_end"
    recovery_messages = [
        message
        for message in messages
        if isinstance(message, AssistantMessage) and message.is_tool_result_recovery
    ]
    assert recovery_messages == []


@pytest.mark.anyio
async def test_image_recovery_respects_max_turns() -> None:
    messages = _image_history()
    provider = FakeProvider(
        [
            [assistant_error("image exceeds maximum size")],
            [assistant_done(AssistantMessage(content="Use a thumbnail."))],
        ]
    )

    events = await _run(provider, messages, max_turns=1)

    assert events[-1].type == "agent_end"
    assert len(provider.calls) == 1


def test_old_images_are_not_removed_for_unrelated_later_errors() -> None:
    messages: list[AgentMessage] = [
        *_image_history(),
        AssistantMessage(content="Use a thumbnail."),
        UserMessage(content="Now summarize."),
        AssistantMessage(content=[ToolCall(id="plain", name="read", arguments={})]),
        ToolResultMessage(
            tool_call_id="plain",
            tool_name="read",
            content=[TextContent(text="plain output")],
        ),
        AssistantMessage(stop_reason="error", error_message="unrelated outage"),
    ]

    context = _provider_context(messages)

    image_result = next(
        message
        for message in context
        if isinstance(message, ToolResultMessage) and message.tool_call_id == "image"
    )
    assert any(isinstance(block, ImageContent) for block in image_result.content)
