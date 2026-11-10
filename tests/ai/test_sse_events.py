"""Framing tests for the single shared SSE event parser.

``_sse.iter_sse_events`` replaced four per-adapter "one ``data:`` line per
event" loops and the codex path's multi-line implementation. These tests pin the
framing rules (multi-line data, CRLF, comments, ``event:`` fields, long lines,
``[DONE]`` ownership) and prove that each adapter produces the same event
sequence for a split-data stream as for the equivalent single-line stream.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import pytest

from baldric.agent import UserMessage
from baldric.ai import (
    AnthropicConfig,
    AnthropicProvider,
    AssistantDoneEvent,
    GoogleGenerativeAIProvider,
    MistralConversationsProvider,
    OpenAICodexConfig,
    OpenAICodexCredentials,
    OpenAICodexProvider,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)
from baldric.ai._sse import SSEEvent, iter_sse_events


async def _lines(*lines: str) -> AsyncIterator[str]:
    for line in lines:
        yield line


async def _parse(*lines: str) -> list[SSEEvent]:
    return [event async for event in iter_sse_events(_lines(*lines))]


async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


@pytest.mark.anyio
async def test_joins_multiline_data_values_with_newlines() -> None:
    events = await _parse('data: {"a":', "data: 1}", "")

    assert events == [SSEEvent(data='{"a":\n1}')]


@pytest.mark.anyio
async def test_captures_event_field_and_ignores_comments_and_unknown_fields() -> None:
    events = await _parse(": keep-alive", "event: message", "id: 42", "data: payload", "")

    assert events == [SSEEvent(data="payload", event="message")]


@pytest.mark.anyio
async def test_dispatches_crlf_frames_and_tolerates_stray_carriage_returns() -> None:
    # httpx splits CRLF into lines; a stray trailing ``\r`` must not break parsing.
    events = await _parse("data: one\r", "", "data: two\r", "\r")

    assert events == [SSEEvent(data="one"), SSEEvent(data="two")]


@pytest.mark.anyio
async def test_dispatches_trailing_event_without_final_blank_line() -> None:
    events = await _parse('data: {"a": 1}')

    assert events == [SSEEvent(data='{"a": 1}')]


@pytest.mark.anyio
async def test_skips_empty_data_frames() -> None:
    assert await _parse("data:", "") == []
    assert await _parse("data:", "", "data: value", "") == [SSEEvent(data="value")]


@pytest.mark.anyio
async def test_leaves_done_sentinel_to_the_caller() -> None:
    events = await _parse("data: [DONE]", "")

    assert events == [SSEEvent(data="[DONE]")]


@pytest.mark.anyio
async def test_ignores_bare_field_names_without_a_value() -> None:
    assert await _parse("data", "") == []


@pytest.mark.anyio
async def test_handles_a_very_long_data_line() -> None:
    payload = json.dumps({"text": "x" * 200_000})
    events = await _parse(f"data: {payload}", "")

    assert events == [SSEEvent(data=payload)]


def _split_at(payload: str, marker: str) -> list[str]:
    """Split one JSON payload at a safe token boundary for multi-line ``data:``."""
    index = payload.index(marker)
    return [payload[:index], payload[index:]]


def _body(*blocks: list[str]) -> str:
    """Render SSE dispatch blocks; each inner list is one event's data lines."""
    return "".join("".join(f"data: {line}\n" for line in block) + "\n" for block in blocks)


def _assert_same_sequence(single: list[object], split: list[object]) -> None:
    assert [event.type for event in single] == [event.type for event in split]
    single_done = single[-1]
    split_done = split[-1]
    assert isinstance(single_done, AssistantDoneEvent)
    assert isinstance(split_done, AssistantDoneEvent)
    assert split_done.message.content == single_done.message.content
    assert split_done.message.usage == single_done.message.usage
    assert split_done.message.stop_reason == single_done.message.stop_reason


@pytest.mark.anyio
async def test_anthropic_adapter_reassembles_split_data_frames() -> None:
    payload = json.dumps(
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "text_delta", "text": "ok"},
        },
        separators=(",", ":"),
    )
    finish = [
        '{"type":"message_delta","delta":{"stop_reason":"end_turn"}}',
        '{"type":"message_stop"}',
    ]
    single_body = _body([payload], [finish[0]], [finish[1]])
    split_body = _body(_split_at(payload, '"index"'), [finish[0]], [finish[1]])

    single = await _stream_anthropic(single_body)
    split = await _stream_anthropic(split_body)

    _assert_same_sequence(single, split)
    assert isinstance(split[-1], AssistantDoneEvent)
    assert split[-1].message.text == "ok"


@pytest.mark.anyio
async def test_google_adapter_reassembles_split_data_frames() -> None:
    payload = json.dumps(
        {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]},
        separators=(",", ":"),
    )
    finish = ['{"candidates":[{"finishReason":"STOP"}]}']
    single_body = _body([payload], finish)
    split_body = _body(_split_at(payload, '"content"'), finish)

    single = await _stream_google(single_body)
    split = await _stream_google(split_body)

    _assert_same_sequence(single, split)
    assert isinstance(split[-1], AssistantDoneEvent)
    assert split[-1].message.text == "ok"


@pytest.mark.anyio
async def test_mistral_adapter_reassembles_split_data_frames() -> None:
    payload = json.dumps({"choices": [{"delta": {"content": "ok"}}]}, separators=(",", ":"))
    finish = ["[DONE]"]
    single_body = _body([payload], finish)
    split_body = _body(_split_at(payload, '"delta"'), finish)

    single = await _stream_mistral(single_body)
    split = await _stream_mistral(split_body)

    _assert_same_sequence(single, split)
    assert isinstance(split[-1], AssistantDoneEvent)
    assert split[-1].message.text == "ok"


@pytest.mark.anyio
async def test_openai_compatible_adapter_reassembles_split_data_frames() -> None:
    payload = json.dumps({"choices": [{"delta": {"content": "ok"}}]}, separators=(",", ":"))
    finish = ["[DONE]"]
    single_body = _body([payload], finish)
    split_body = _body(_split_at(payload, '"delta"'), finish)

    single = await _stream_openai_compatible(single_body)
    split = await _stream_openai_compatible(split_body)

    _assert_same_sequence(single, split)
    assert isinstance(split[-1], AssistantDoneEvent)
    assert split[-1].message.text == "ok"


@pytest.mark.anyio
async def test_codex_adapter_reassembles_split_data_frames() -> None:
    payload = json.dumps(
        {"type": "response.output_text.delta", "delta": "ok"},
        separators=(",", ":"),
    )
    finish = ['{"type":"response.completed","response":{"status":"completed"}}']
    single_body = _body([payload], finish)
    split_body = _body(_split_at(payload, '"delta"'), finish)

    single = await _stream_codex(single_body)
    split = await _stream_codex(split_body)

    _assert_same_sequence(single, split)
    assert isinstance(split[-1], AssistantDoneEvent)
    assert split[-1].message.text == "ok"


async def _stream_anthropic(body: str) -> list[object]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = AnthropicProvider(
            AnthropicConfig(api_key="test-key", base_url="https://api.anthropic.test/v1"),
            client=client,
        )
        return await _collect(
            provider.stream_response(
                model="claude-test",
                system="You are Baldric.",
                messages=[UserMessage(content="Say ok")],
                tools=[],
            )
        )


async def _stream_google(body: str) -> list[object]:
    return await _stream_openai_style(GoogleGenerativeAIProvider, body, "gemini-test")


async def _stream_mistral(body: str) -> list[object]:
    return await _stream_openai_style(MistralConversationsProvider, body, "mistral-test")


async def _stream_openai_compatible(body: str) -> list[object]:
    return await _stream_openai_style(OpenAICompatibleProvider, body, "model-test")


async def _stream_openai_style(
    provider_cls: type[OpenAICompatibleProvider]
    | type[GoogleGenerativeAIProvider]
    | type[MistralConversationsProvider],
    body: str,
    model: str,
) -> list[object]:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = provider_cls(
            OpenAICompatibleConfig(api_key="test-key", base_url="https://example.test/v1"),
            client=client,
        )
        return await _collect(
            provider.stream_response(
                model=model,
                system="You are Baldric.",
                messages=[UserMessage(content="Say ok")],
                tools=[],
            )
        )


async def _stream_codex(body: str) -> list[object]:
    async def credentials() -> OpenAICodexCredentials:
        return OpenAICodexCredentials(access_token="access-token", account_id="account-1")

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICodexProvider(
            OpenAICodexConfig(
                credential_resolver=credentials,
                base_url="https://chatgpt.test/backend-api",
            ),
            client=client,
        )
        return await _collect(
            provider.stream_response(
                model="gpt-test",
                system="You are Baldric.",
                messages=[UserMessage(content="Say ok")],
                tools=[],
            )
        )
