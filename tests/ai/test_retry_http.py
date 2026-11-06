"""HTTP retry integration: server guidance reaches the real request path."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from baldric_agent import UserMessage
from baldric_ai import (
    AssistantErrorEvent,
    AssistantMessageEvent,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)

_SSE_BODY = 'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'


async def _collect(stream: AsyncIterator[AssistantMessageEvent]) -> list[AssistantMessageEvent]:
    return [event async for event in stream]


@pytest.mark.anyio
async def test_a_server_requested_delay_is_used_on_the_request_path() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(429, headers={"retry-after": "0.01"}, text="slow down")
        return httpx.Response(
            200,
            text=_SSE_BODY,
            headers={"content-type": "text/event-stream"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            OpenAICompatibleConfig(
                api_key="test-key",
                base_url="https://example.test/v1",
                max_retries=1,
                max_retry_delay_seconds=1,
            ),
            client=client,
        )
        events = await _collect(
            provider.stream_response(
                model="test-model",
                system="",
                messages=[UserMessage(content="Hi")],
                tools=[],
            )
        )

    assert len(requests) == 2
    assert events[-1].type == "done"


@pytest.mark.anyio
async def test_a_delay_above_the_limit_fails_fast_with_a_code() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(429, headers={"retry-after": "60"}, text="slow down")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            OpenAICompatibleConfig(
                api_key="test-key",
                provider_name="test-openai",
                base_url="https://example.test/v1",
                max_retries=3,
                max_retry_delay_seconds=1,
            ),
            client=client,
        )
        events = await _collect(
            provider.stream_response(
                model="test-model",
                system="",
                messages=[UserMessage(content="Hi")],
                tools=[],
            )
        )

    assert len(requests) == 1
    assert isinstance(events[-1], AssistantErrorEvent)
    error = events[-1].error
    assert "status 429" in (error.error_message or "")
    assert "Server asked to wait 60s" in (error.error_message or "")
    assert error.diagnostics is not None
    assert error.diagnostics[0].details is not None
    details = error.diagnostics[0].details
    assert isinstance(details, dict)
    assert details["code"] == "retry_after_too_long"


@pytest.mark.anyio
async def test_a_context_overflow_body_is_not_retried() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            400,
            json={"error": {"message": "This model's maximum context length is 8192 tokens"}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            OpenAICompatibleConfig(
                api_key="test-key",
                provider_name="test-openai",
                base_url="https://example.test/v1",
                max_retries=3,
                max_retry_delay_seconds=0,
            ),
            client=client,
        )
        events = await _collect(
            provider.stream_response(
                model="test-model",
                system="",
                messages=[UserMessage(content="Hi")],
                tools=[],
            )
        )

    assert len(requests) == 1
    assert isinstance(events[-1], AssistantErrorEvent)
    error = events[-1].error
    assert error.diagnostics is not None
    details = error.diagnostics[0].details
    assert isinstance(details, dict)
    assert details["code"] == "context_overflow"
