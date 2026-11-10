"""Codex tool-call identity: portable ids on the wire, private item ids in memory.

The adapter used to encode the Codex response item id into the provider-neutral
``ToolCall.id`` as ``f"{call_id}|{item_id}"``. That bypassed
``tool_call_ids.portable_tool_call_id`` and made the item id unrecoverable after
a cross-provider replay. These tests pin the split: the durable id is only the
normalised call id, and the private item id survives round-trips through the
adapter's own mapping.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from json import loads

import httpx
import pytest

from baldric.agent import AssistantMessage, ToolResultMessage, UserMessage
from baldric.ai import (
    AssistantDoneEvent,
    OpenAICodexConfig,
    OpenAICodexCredentials,
    OpenAICodexProvider,
    ToolCallEndEvent,
)
from baldric.ai.tool_call_ids import portable_tool_call_id


async def _collect(stream: AsyncIterator[object]) -> list[object]:
    return [event async for event in stream]


async def _credentials() -> OpenAICodexCredentials:
    return OpenAICodexCredentials(access_token="access-token", account_id="account-1")


def _sse(*events: object) -> str:
    return "".join(f"data: {json.dumps(event, separators=(',', ':'))}\n\n" for event in events)


def _tool_call_stream(*, call_id: str, item_id: str | None) -> str:
    base_item: dict[str, object] = {
        "type": "function_call",
        "call_id": call_id,
        "name": "read",
    }
    if item_id is not None:
        base_item["id"] = item_id
    added_item = {**base_item, "arguments": ""}
    done_item = {**base_item, "arguments": '{"path":"a.txt"}'}
    events: list[object] = [
        {"type": "response.output_item.added", "output_index": 0, "item": added_item},
        {
            "type": "response.function_call_arguments.delta",
            "item_id": item_id or "",
            "output_index": 0,
            "delta": '{"path":"a.txt"}',
        },
        {
            "type": "response.function_call_arguments.done",
            "item_id": item_id or "",
            "output_index": 0,
            "arguments": '{"path":"a.txt"}',
        },
        {"type": "response.output_item.done", "output_index": 0, "item": done_item},
        {"type": "response.completed", "response": {"status": "completed"}},
    ]
    return _sse(*events)


_TEXT_STREAM = _sse(
    {"type": "response.output_text.delta", "delta": "done"},
    {"type": "response.completed", "response": {"status": "completed"}},
)


def _provider(client: httpx.AsyncClient) -> OpenAICodexProvider:
    return OpenAICodexProvider(
        OpenAICodexConfig(
            credential_resolver=_credentials,
            base_url="https://chatgpt.test/backend-api",
        ),
        client=client,
    )


async def _request_tool_call(provider: OpenAICodexProvider) -> tuple[list[object], AssistantMessage]:
    events = await _collect(
        provider.stream_response(
            model="gpt-test",
            system="You are Baldric.",
            messages=[UserMessage(content="Read a.txt")],
            tools=[],
        )
    )
    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    return events, done.message


async def _replay(provider: OpenAICodexProvider, assistant: AssistantMessage) -> None:
    history = [
        UserMessage(content="Read a.txt"),
        assistant,
        ToolResultMessage(
            tool_call_id=assistant.tool_calls[0].id,
            tool_name=assistant.tool_calls[0].name,
            content="file body",
        ),
    ]
    await _collect(
        provider.stream_response(
            model="gpt-test",
            system="You are Baldric.",
            messages=history,
            tools=[],
        )
    )


@pytest.mark.anyio
async def test_tool_call_id_is_the_portable_call_id_and_item_id_round_trips() -> None:
    requests: list[httpx.Request] = []
    bodies = [_tool_call_stream(call_id="call_abc", item_id="fc_1"), _TEXT_STREAM]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=bodies[len(requests) - 1],
            headers={"content-type": "text/event-stream"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = _provider(client)
        events, assistant = await _request_tool_call(provider)
        await _replay(provider, assistant)

    tool_calls = [event.tool_call for event in events if isinstance(event, ToolCallEndEvent)]
    assert tuple(tool_calls) == assistant.tool_calls
    assert tool_calls[0].id == "call_abc"
    assert "|" not in tool_calls[0].id

    replayed = loads(requests[1].content)["input"]
    function_call = replayed[1]
    assert function_call == {
        "type": "function_call",
        "call_id": "call_abc",
        "name": "read",
        "arguments": '{"path": "a.txt"}',
        "id": "fc_1",
    }
    assert replayed[2] == {
        "type": "function_call_output",
        "call_id": "call_abc",
        "output": "file body",
    }


@pytest.mark.anyio
async def test_native_call_id_requiring_normalisation_still_round_trips_item_id() -> None:
    native_call_id = "call|weird/id"
    requests: list[httpx.Request] = []
    bodies = [_tool_call_stream(call_id=native_call_id, item_id="fc_9"), _TEXT_STREAM]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=bodies[len(requests) - 1],
            headers={"content-type": "text/event-stream"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = _provider(client)
        _events, assistant = await _request_tool_call(provider)
        await _replay(provider, assistant)

    durable_id = assistant.tool_calls[0].id
    assert durable_id == portable_tool_call_id(native_call_id)
    assert "|" not in durable_id

    replayed = loads(requests[1].content)["input"]
    assert replayed[1]["call_id"] == durable_id
    assert replayed[1]["id"] == "fc_9"
    assert replayed[2]["call_id"] == durable_id


@pytest.mark.anyio
async def test_missing_item_id_is_omitted_from_replay_instead_of_encoded() -> None:
    requests: list[httpx.Request] = []
    bodies = [_tool_call_stream(call_id="call_1", item_id=None), _TEXT_STREAM]

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            text=bodies[len(requests) - 1],
            headers={"content-type": "text/event-stream"},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = _provider(client)
        _events, assistant = await _request_tool_call(provider)
        await _replay(provider, assistant)

    assert assistant.tool_calls[0].id == "call_1"
    replayed = loads(requests[1].content)["input"]
    assert replayed[1]["call_id"] == "call_1"
    assert "id" not in replayed[1]
