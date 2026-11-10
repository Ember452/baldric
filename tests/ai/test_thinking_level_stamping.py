"""AssistantMessage.thinking_level is stamped with the requested level.

Pi semantics (pi-ai types.ts:603): the level the request asked for, not the
provider-native effective value. Stamped once in the canonicalize funnel;
adapters derive it from their config's reasoning effort ("none" is the wire
spelling of the "off" level) and pass it through. Absent when the config
carries no level.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from baldric.ai._provider_events import (
    ProviderEvent,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderTextDeltaEvent,
)
from baldric.ai.env import OpenAICompatibleConfig, thinking_level_from_effort
from baldric.ai.events import AssistantDoneEvent, AssistantStartEvent
from baldric.ai.openai_compatible import OpenAICompatibleProvider
from baldric.ai.stream import canonicalize_provider_stream
from baldric.protocol.messages import AssistantMessage, UserMessage


async def _source(events: list[ProviderEvent]) -> AsyncIterator[ProviderEvent]:
    for event in events:
        yield event


def _end(text: str) -> ProviderResponseEndEvent:
    return ProviderResponseEndEvent(
        message=AssistantMessage(content=text, usage=None),
        finish_reason="stop",
    )


@pytest.mark.anyio
async def test_canonicalize_stamps_requested_level_on_start_and_done() -> None:
    events = [
        event
        async for event in canonicalize_provider_stream(
            _source(
                [
                    ProviderResponseStartEvent(model="m"),
                    ProviderTextDeltaEvent(delta="hi"),
                    _end("hi"),
                ]
            ),
            api="test",
            provider="p",
            model="m",
            thinking_level="medium",
        )
    ]

    starts = [event for event in events if isinstance(event, AssistantStartEvent)]
    dones = [event for event in events if isinstance(event, AssistantDoneEvent)]
    assert starts[0].partial.thinking_level == "medium"
    assert dones[0].message.thinking_level == "medium"


@pytest.mark.anyio
async def test_canonicalize_leaves_level_absent_without_a_level() -> None:
    events = [
        event
        async for event in canonicalize_provider_stream(
            _source([ProviderResponseStartEvent(model="m"), _end("hi")]),
            api="test",
            provider="p",
            model="m",
        )
    ]

    dones = [event for event in events if isinstance(event, AssistantDoneEvent)]
    assert dones[0].message.thinking_level is None


def test_thinking_level_from_effort_inverts_the_wire_spelling() -> None:
    assert thinking_level_from_effort(None) is None
    assert thinking_level_from_effort("none") == "off"
    assert thinking_level_from_effort("high") == "high"


def _sse_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        text=('data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'),
        headers={"content-type": "text/event-stream"},
    )


async def _stream_once(config: OpenAICompatibleConfig) -> AssistantMessage:
    async with httpx.AsyncClient(transport=httpx.MockTransport(_sse_handler)) as client:
        provider = OpenAICompatibleProvider(config, client=client)
        done: AssistantMessage | None = None
        async for event in provider.stream_response(
            model="test-model",
            system="s",
            messages=[UserMessage(content="hi")],
            tools=[],
        ):
            if isinstance(event, AssistantDoneEvent):
                done = event.message
    assert done is not None
    return done


@pytest.mark.anyio
async def test_openai_compatible_stamps_the_configured_level() -> None:
    done = await _stream_once(
        OpenAICompatibleConfig(
            api_key="test-key",
            base_url="https://example.test/v1",
            reasoning_effort="high",
        )
    )
    assert done.thinking_level == "high"


@pytest.mark.anyio
async def test_openai_compatible_leaves_the_level_absent_without_effort() -> None:
    done = await _stream_once(OpenAICompatibleConfig(api_key="test-key", base_url="https://example.test/v1"))
    assert done.thinking_level is None
