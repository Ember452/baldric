"""Codex transport retries must not replay already-emitted thinking.

The transport-error retry branch guarded only ``emitted_content``; a stream that
had already emitted reasoning deltas was retried and the second attempt
re-emitted the same thinking into the durable history. The in-stream error
branch already guards both flags, and the other adapters fold thinking into
their content flag; this pins the same contract for mid-stream transport
failures on Codex.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from baldric.agent import UserMessage
from baldric.ai import (
    OpenAICodexConfig,
    OpenAICodexCredentials,
    OpenAICodexProvider,
    ThinkingDeltaEvent,
)

pytestmark = pytest.mark.anyio


def _sse(*events: object) -> str:
    return "".join(f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in events)


_THINKING_FRAME = _sse({"type": "response.reasoning_summary_text.delta", "delta": "thought-1"})


async def _credentials() -> OpenAICodexCredentials:
    return OpenAICodexCredentials(access_token="access-token", account_id="account-1")


async def _thinking_then_reset() -> AsyncIterator[bytes]:
    yield _THINKING_FRAME.encode("utf-8")
    raise httpx.ReadError("connection reset mid-stream")


async def _stream_once() -> tuple[list[httpx.Request], list[object]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            content=_thinking_then_reset(),
            headers={"content-type": "text/event-stream"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICodexProvider(
            OpenAICodexConfig(
                credential_resolver=_credentials,
                base_url="https://chatgpt.test/backend-api",
                max_retries=2,
            ),
            client=client,
        )
        events = [
            event
            async for event in provider.stream_response(
                model="gpt-test",
                system="You are Baldric.",
                messages=[UserMessage(content="Think, then answer.")],
                tools=[],
            )
        ]
    return requests, events


async def test_transport_error_after_thinking_fails_instead_of_replaying() -> None:
    requests, events = await _stream_once()

    thinking = [event for event in events if isinstance(event, ThinkingDeltaEvent)]
    assert [event.delta for event in thinking] == ["thought-1"]
    assert len(requests) == 1
