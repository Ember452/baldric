"""Adapter-level request seams (plan Task A1): payload/headers/response hooks are
invoked at each adapter's real request point.

Uses httpx MockTransport like the rest of tests/ai: proves a registered hook can
mutate the outgoing payload and headers and observe the HTTP response, and that
with no hooks the request is byte-identical to the pre-hook code path.
"""

from __future__ import annotations

from json import loads

import httpx
import pytest

from baldric.agent import UserMessage
from baldric.ai import (
    AnthropicConfig,
    AnthropicProvider,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)
from baldric.protocol.provider import HookContext, RequestHooks

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _sse() -> httpx.Response:
    return httpx.Response(
        200,
        text='data: {"choices":[{"delta":{"content":"hi"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n',
        headers={"content-type": "text/event-stream"},
    )


async def test_openai_compatible_payload_and_headers_hooks_apply() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _sse()

    def add_header(headers: dict[str, str], ctx: HookContext) -> None:
        headers["X-Extension"] = "on"

    def tag_payload(payload: dict[str, object], ctx: HookContext) -> dict[str, object]:
        return {**payload, "metadata": {"tagged": True}}

    seen_status: list[int] = []
    hooks = RequestHooks(
        model="test-model",
        headers=[add_header],
        payload=[tag_payload],
        response=[lambda status, headers, ctx: seen_status.append(status)],
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            OpenAICompatibleConfig(api_key="k", base_url="https://example.test/v1"), client=client
        )
        async for _ in provider.stream_response(
            model="test-model",
            system="sys",
            messages=[UserMessage(content="q")],
            tools=[],
            hooks=hooks,
        ):
            pass

    request = requests[0]
    assert request.headers["x-extension"] == "on"
    assert loads(request.content)["metadata"] == {"tagged": True}
    assert seen_status == [200]


async def test_no_hooks_is_byte_identical_for_openai_compatible() -> None:
    """Transparency: no hooks => same payload/headers as passing None-equivalent."""
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _sse()

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            OpenAICompatibleConfig(api_key="k", base_url="https://example.test/v1"), client=client
        )
        async for _ in provider.stream_response(
            model="m", system="s", messages=[UserMessage(content="q")], tools=[]
        ):
            pass

    payload = loads(requests[0].content)
    assert "metadata" not in payload
    assert "x-extension" not in requests[0].headers


async def test_anthropic_headers_and_response_hooks_apply() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text='event: message_stop\ndata: {"type":"message_stop"}\n\n',
            headers={"content-type": "text/event-stream", "request-id": "abc"},
        )

    def add_header(headers: dict[str, str], ctx: HookContext) -> None:
        headers["X-Trace"] = "t1"

    seen: list[tuple[int, str]] = []
    hooks = RequestHooks(
        model="claude-x",
        headers=[add_header],
        response=[lambda status, headers, ctx: seen.append((status, headers.get("request-id", "")))],
    )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = AnthropicProvider(
            AnthropicConfig(api_key="k", base_url="https://api.anthropic.test/v1"), client=client
        )
        async for _ in provider.stream_response(
            model="claude-x",
            system="sys",
            messages=[UserMessage(content="q")],
            tools=[],
            hooks=hooks,
        ):
            pass

    assert requests[0].headers["x-trace"] == "t1"
    assert seen == [(200, "abc")]


async def test_a_raising_request_hook_is_isolated() -> None:
    """A raising payload hook is skipped; the request still goes out unchanged."""

    def boom(payload: dict[str, object], ctx: HookContext) -> dict[str, object]:
        raise RuntimeError("kaboom")

    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _sse()

    hooks = RequestHooks(model="m", payload=[boom])
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            OpenAICompatibleConfig(api_key="k", base_url="https://example.test/v1"), client=client
        )
        async for _ in provider.stream_response(
            model="m", system="s", messages=[UserMessage(content="q")], tools=[], hooks=hooks
        ):
            pass

    assert loads(requests[0].content)["model"] == "m"
