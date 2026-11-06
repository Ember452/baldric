"""Provider-stream to agent-event translation for the loop."""

from __future__ import annotations

from collections.abc import AsyncIterator
from time import monotonic_ns

from baldric_agent.events import (
    AgentEvent,
    MessageEndEvent,
    MessageStartEvent,
    MessageUpdateEvent,
)
from baldric_agent.messages import AgentMessage, ResponseTiming
from baldric_agent.provider import CancellationToken, ModelProvider
from baldric_agent.provider_events import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantMessageEvent,
    AssistantStartEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallDeltaEvent,
    ToolCallEndEvent,
    ToolCallStartEvent,
)
from baldric_agent.tools import AgentTool


async def assistant_events(
    *,
    provider: ModelProvider,
    model: str,
    system: str,
    messages: list[AgentMessage],
    tools: list[AgentTool],
    signal: CancellationToken | None,
    session_id: str | None,
) -> AsyncIterator[AgentEvent]:
    """Translate one provider stream into message lifecycle events."""
    source: AsyncIterator[AssistantMessageEvent] = provider.stream_response(
        model=model,
        system=system,
        messages=messages,
        tools=tools,
        signal=signal,
        session_id=session_id,
    )
    started = False
    provider_elapsed_ns = 0
    first_output_elapsed_ns: int | None = None
    source_iterator = source.__aiter__()
    while True:
        wait_started_ns = monotonic_ns()
        try:
            event = await anext(source_iterator)
        except StopAsyncIteration:
            break
        provider_elapsed_ns += max(0, monotonic_ns() - wait_started_ns)
        if first_output_elapsed_ns is None and isinstance(
            event,
            (
                TextDeltaEvent,
                ThinkingDeltaEvent,
                ToolCallStartEvent,
                ToolCallDeltaEvent,
                ToolCallEndEvent,
            ),
        ):
            first_output_elapsed_ns = provider_elapsed_ns
        if isinstance(event, AssistantStartEvent):
            started = True
            yield MessageStartEvent(message=event.partial)
        elif isinstance(event, AssistantDoneEvent):
            event.message.timing = response_timing(
                first_output_elapsed_ns,
                provider_elapsed_ns,
            )
            if not started:
                yield MessageStartEvent(message=event.message)
            yield MessageEndEvent(message=event.message)
        elif isinstance(event, AssistantErrorEvent):
            if signal is not None and signal.is_cancelled():
                # A cancelled run ends as aborted, not as a provider failure: the
                # stream often stops because the response was closed, and users
                # must not see their own cancellation reported as an error.
                event.error.stop_reason = "aborted"
                event.error.error_message = "Operation aborted"
            event.error.timing = response_timing(
                first_output_elapsed_ns,
                provider_elapsed_ns,
            )
            if not started:
                yield MessageStartEvent(message=event.error)
            yield MessageEndEvent(message=event.error)
        else:
            yield MessageUpdateEvent(
                message=event.partial,
                assistant_message_event=event,
            )


def response_timing(
    first_output_elapsed_ns: int | None,
    total_elapsed_ns: int,
) -> ResponseTiming:
    """Build persistable durations from time spent awaiting provider events."""
    return ResponseTiming(
        time_to_first_output_ms=(
            first_output_elapsed_ns // 1_000_000 if first_output_elapsed_ns is not None else None
        ),
        total_duration_ms=total_elapsed_ns // 1_000_000,
    )
