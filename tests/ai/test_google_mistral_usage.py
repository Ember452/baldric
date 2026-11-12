"""Usage parsing for the Google and Mistral adapters.

Both adapters emitted ``AssistantMessage(usage=Usage())`` unconditionally, which
made every downstream token/cost/context number zero and disabled the provider
usage branch of the compaction window. These tests pin the field mapping
(including cache reads and thinking tokens) and the "not reported stays zero"
contract on realistic response shapes.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from baldric.agent import Usage, UserMessage
from baldric.ai import (
    AssistantDoneEvent,
    GoogleGenerativeAIProvider,
    MistralConversationsProvider,
    OpenAICompatibleConfig,
)

_CONFIG = OpenAICompatibleConfig(api_key="test-key", base_url="https://example.test/v1")


async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


def _sse(*frames: object) -> str:
    return "".join(f"data: {json.dumps(frame, separators=(',', ':'))}\n\n" for frame in frames)


def _done_usage(events: list[object]) -> Usage:
    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    return done.message.usage


async def _run_google(body: str) -> list[object]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleGenerativeAIProvider(_CONFIG, client=client)
        return await _collect(
            provider.stream_response(
                model="gemini-test",
                system="You are Baldric.",
                messages=[UserMessage(content="Say hi")],
                tools=[],
            )
        )


async def _run_mistral(body: str) -> list[object]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MistralConversationsProvider(_CONFIG, client=client)
        return await _collect(
            provider.stream_response(
                model="mistral-test",
                system="You are Baldric.",
                messages=[UserMessage(content="Say hi")],
                tools=[],
            )
        )


def _google_text(text: str) -> dict[str, object]:
    return {"candidates": [{"content": {"parts": [{"text": text}], "role": "model"}, "index": 0}]}


def _google_finish() -> dict[str, object]:
    return {"candidates": [{"content": {"parts": [], "role": "model"}, "finishReason": "STOP", "index": 0}]}


_GOOGLE_USAGE = {
    "promptTokenCount": 1200,
    "candidatesTokenCount": 30,
    "cachedContentTokenCount": 200,
    "thoughtsTokenCount": 10,
    "totalTokenCount": 1240,
}


@pytest.mark.anyio
async def test_google_parses_usage_metadata() -> None:
    body = _sse(
        _google_text("hi"),
        {**_google_finish(), "usageMetadata": _GOOGLE_USAGE},
    )

    usage = _done_usage(await _run_google(body))

    # cached prompt tokens are a cache read, not fresh input; thinking tokens
    # are billed as output and reported separately as reasoning.
    assert usage == Usage(
        input=1000,
        output=40,
        cache_read=200,
        cache_write=0,
        reasoning=10,
        total_tokens=1240,
    )


@pytest.mark.anyio
async def test_google_parses_usage_only_final_chunk() -> None:
    body = _sse(_google_text("hi"), _google_finish(), {"usageMetadata": _GOOGLE_USAGE})

    usage = _done_usage(await _run_google(body))

    assert usage == Usage(
        input=1000,
        output=40,
        cache_read=200,
        cache_write=0,
        reasoning=10,
        total_tokens=1240,
    )


@pytest.mark.anyio
async def test_google_leaves_usage_zero_when_not_reported() -> None:
    body = _sse(_google_text("hi"), _google_finish())

    assert _done_usage(await _run_google(body)) == Usage()


@pytest.mark.anyio
async def test_google_tolerates_malformed_usage_metadata() -> None:
    body = _sse(_google_text("hi"), {**_google_finish(), "usageMetadata": "not-an-object"})

    assert _done_usage(await _run_google(body)) == Usage()


def _mistral_chunk(delta: dict[str, object], finish_reason: str | None = None) -> dict[str, object]:
    return {
        "id": "response-1",
        "object": "chat.completion.chunk",
        "model": "mistral-test",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


@pytest.mark.anyio
async def test_mistral_parses_streamed_usage() -> None:
    body = _sse(
        _mistral_chunk({"content": "hi"}),
        {
            **_mistral_chunk({}, finish_reason="stop"),
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
                "prompt_tokens_details": {"cached_tokens": 3},
            },
        },
    )

    usage = _done_usage(await _run_mistral(body))

    assert usage == Usage(
        input=7,
        output=4,
        cache_read=3,
        cache_write=0,
        total_tokens=14,
    )


@pytest.mark.anyio
async def test_mistral_parses_usage_only_final_chunk() -> None:
    body = _sse(
        _mistral_chunk({"content": "hi"}),
        _mistral_chunk({}, finish_reason="stop"),
        {
            "id": "response-1",
            "object": "chat.completion.chunk",
            "choices": [],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
            },
        },
    )

    usage = _done_usage(await _run_mistral(body))

    assert usage == Usage(input=10, output=4, cache_read=0, cache_write=0, total_tokens=14)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "cached_details",
    [
        {"prompt_tokens_details": {"cached_tokens": 3}},
        {"promptTokensDetails": {"cachedTokens": 3}},
        {"prompt_token_details": {"cached_tokens": 3}},
        {"promptTokenDetails": {"cachedTokens": 3}},
        {"num_cached_tokens": 3},
        {"numCachedTokens": 3},
    ],
)
async def test_mistral_reads_cached_tokens_across_field_spellings(
    cached_details: dict[str, object],
) -> None:
    body = _sse(
        _mistral_chunk({"content": "hi"}),
        {
            **_mistral_chunk({}, finish_reason="stop"),
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 4,
                "total_tokens": 14,
                **cached_details,
            },
        },
    )

    usage = _done_usage(await _run_mistral(body))

    assert usage == Usage(input=7, output=4, cache_read=3, cache_write=0, total_tokens=14)


@pytest.mark.anyio
async def test_mistral_leaves_usage_zero_when_not_reported() -> None:
    body = _sse(_mistral_chunk({"content": "hi"}), _mistral_chunk({}, finish_reason="stop"))

    assert _done_usage(await _run_mistral(body)) == Usage()


async def _collect_google_request(config: OpenAICompatibleConfig) -> httpx.Request:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=_sse(_google_text("hi"), _google_finish()),
            headers={"content-type": "text/event-stream"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = GoogleGenerativeAIProvider(config, client=client)
        await _collect(
            provider.stream_response(
                model="gemini-test",
                system="You are Baldric.",
                messages=[UserMessage(content="Say hi")],
                tools=[],
            )
        )
    return requests[0]


@pytest.mark.anyio
async def test_google_auth_uses_header_instead_of_url_query() -> None:
    request = await _collect_google_request(_CONFIG)

    assert "key" not in request.url.params
    assert request.headers["x-goog-api-key"] == "test-key"


@pytest.mark.anyio
async def test_google_explicit_auth_header_wins_over_config_api_key() -> None:
    config = OpenAICompatibleConfig(
        api_key="test-key",
        base_url="https://example.test/v1",
        headers={"x-goog-api-key": "user-key"},
    )

    request = await _collect_google_request(config)

    assert request.headers["x-goog-api-key"] == "user-key"
    assert "key" not in request.url.params


async def _capture_mistral_payload(model: str, *, reasoning_effort: str | None) -> dict[str, object]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=_sse(
                _mistral_chunk({"content": "hi"}),
                _mistral_chunk({}, finish_reason="stop"),
            ),
            headers={"content-type": "text/event-stream"},
        )

    config = OpenAICompatibleConfig(
        api_key="test-key",
        base_url="https://example.test/v1",
        reasoning_effort=reasoning_effort,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = MistralConversationsProvider(config, client=client)
        await _collect(
            provider.stream_response(
                model=model,
                system="You are Baldric.",
                messages=[UserMessage(content="Say hi")],
                tools=[],
            )
        )
    return json.loads(requests[0].content.decode("utf-8"))


@pytest.mark.anyio
async def test_mistral_thinking_off_sends_reasoning_effort_none() -> None:
    # pi: mistral-conversations.ts:200-206 — effort-map models always carry
    # reasoning_effort; "none" is how thinking-off reaches the API.
    payload = await _capture_mistral_payload("mistral-small-latest", reasoning_effort="none")

    assert payload["reasoning_effort"] == "none"


@pytest.mark.anyio
async def test_mistral_unsupported_levels_clamp_to_high() -> None:
    for level in ("minimal", "low", "medium", "xhigh", "max"):
        payload = await _capture_mistral_payload("mistral-small-latest", reasoning_effort=level)

        assert payload["reasoning_effort"] == "high", level


@pytest.mark.anyio
async def test_mistral_unconfigured_effort_stays_omitted() -> None:
    payload = await _capture_mistral_payload("mistral-small-latest", reasoning_effort=None)

    assert "reasoning_effort" not in payload


@pytest.mark.anyio
async def test_mistral_non_effort_models_use_prompt_mode() -> None:
    payload = await _capture_mistral_payload("magistral-medium-latest", reasoning_effort="medium")

    assert payload["prompt_mode"] == "reasoning"
    assert "reasoning_effort" not in payload
