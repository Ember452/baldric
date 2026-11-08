"""Provider retry details reach durable diagnostics; the retry delay cap fits a 429.

``ProviderRetryEvent.data`` (status code, response body, error code) was dropped
at the canonicalizer because the public retry events have no details slot. It now
flows through ``AssistantMessage.diagnostics`` (same path as provider errors),
bounded so an HTTP body cannot grow the persisted message without limit.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest

from baldric_agent import AssistantMessage, TextContent, UserMessage
from baldric_ai import (
    AssistantDoneEvent,
    AssistantErrorEvent,
    AssistantRetryEvent,
    AssistantStartEvent,
    OpenAICompatibleConfig,
    OpenAICompatibleProvider,
)
from baldric_ai._provider_events import (
    ProviderErrorEvent,
    ProviderEvent,
    ProviderResponseEndEvent,
    ProviderResponseStartEvent,
    ProviderRetryEvent,
)
from baldric_ai.env import (
    DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS,
    openai_compatible_config_from_env,
)
from baldric_ai.stream import canonicalize_provider_stream
from baldric_protocol.messages import AssistantMessageDiagnostic

_SSE_BODY = 'data: {"choices":[{"delta":{"content":"Hi"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'


async def _canonicalize(events: list[ProviderEvent]) -> list[object]:
    async def source() -> AsyncIterator[ProviderEvent]:
        for event in events:
            yield event

    return [
        event
        async for event in canonicalize_provider_stream(
            source(), api="test-api", provider="test-provider", model="test-model"
        )
    ]


def _retry(data: dict[str, object] | None) -> ProviderRetryEvent:
    return ProviderRetryEvent(
        attempt=0,
        max_attempts=2,
        delay_seconds=0.5,
        message="HTTP 429",
        data=data,
    )  # type: ignore[arg-type]


def _response_end() -> ProviderResponseEndEvent:
    return ProviderResponseEndEvent(
        message=AssistantMessage(content=[TextContent(text="ok")]),
        finish_reason="stop",
    )


def _diagnostics(message: AssistantMessage) -> list[AssistantMessageDiagnostic]:
    assert message.diagnostics is not None
    return message.diagnostics


@pytest.mark.anyio
async def test_retry_data_reaches_partial_and_final_message_diagnostics() -> None:
    data = {"status_code": 429, "body": "slow down", "code": "rate_limit"}
    events = await _canonicalize(
        [_retry(data), ProviderResponseStartEvent(model="test-model"), _response_end()]
    )

    retry = next(event for event in events if isinstance(event, AssistantRetryEvent))
    assert retry.message == "HTTP 429"
    start = next(event for event in events if isinstance(event, AssistantStartEvent))
    assert [(item.type, item.details) for item in start.partial.diagnostics or []] == [
        ("provider_retry", data)
    ]
    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    assert [(item.type, item.details) for item in _diagnostics(done.message)] == [("provider_retry", data)]


@pytest.mark.anyio
async def test_retry_data_survives_alongside_a_terminal_provider_error() -> None:
    retry_data = {"status_code": 500, "body": "upstream exploded", "code": "server_error"}
    error_data = {"status_code": 500, "body": "final failure", "attempts": 2, "code": "server_error"}
    events = await _canonicalize(
        [
            _retry(retry_data),
            ProviderErrorEvent(message="Provider failed", data=error_data),
        ]
    )

    error = events[-1]
    assert isinstance(error, AssistantErrorEvent)
    assert [(item.type, item.details) for item in _diagnostics(error.error)] == [
        ("provider_error", error_data),
        ("provider_retry", retry_data),
    ]


@pytest.mark.anyio
async def test_retry_body_is_truncated_before_it_reaches_diagnostics() -> None:
    body = "x" * 900
    events = await _canonicalize(
        [
            _retry({"status_code": 429, "body": body, "code": "rate_limit"}),
            ProviderResponseStartEvent(model="test-model"),
            _response_end(),
        ]
    )

    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    details = _diagnostics(done.message)[0].details
    assert details is not None
    assert details["status_code"] == 429
    assert details["code"] == "rate_limit"
    assert details["body"] == "x" * 500
    assert len(details["body"]) == 500


@pytest.mark.anyio
async def test_retry_without_provider_data_adds_no_diagnostic() -> None:
    events = await _canonicalize(
        [_retry(None), ProviderResponseStartEvent(model="test-model"), _response_end()]
    )

    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    assert done.message.diagnostics is None


@pytest.mark.anyio
async def test_http_retry_details_reach_the_done_message_end_to_end() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"content-type": "application/json"},
                text='{"error":{"message":"rate limited"}}',
            )
        return httpx.Response(200, text=_SSE_BODY, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            OpenAICompatibleConfig(
                api_key="test-key",
                base_url="https://example.test/v1",
                max_retries=1,
                max_retry_delay_seconds=0,
            ),
            client=client,
        )
        events = [
            event
            async for event in provider.stream_response(
                model="test-model",
                system="",
                messages=[UserMessage(content="Hi")],
                tools=[],
            )
        ]

    assert len(requests) == 2
    assert any(isinstance(event, AssistantRetryEvent) for event in events)
    done = events[-1]
    assert isinstance(done, AssistantDoneEvent)
    retry_diagnostics = [item for item in _diagnostics(done.message) if item.type == "provider_retry"]
    assert len(retry_diagnostics) == 1
    details = retry_diagnostics[0].details
    assert details is not None
    assert details["status_code"] == 429
    assert '"rate limited"' in str(details["body"])


@pytest.mark.anyio
async def test_retry_diagnostics_stay_out_of_the_next_model_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(
                429,
                headers={"content-type": "application/json"},
                text='{"error":{"message":"rate limited"}}',
            )
        return httpx.Response(200, text=_SSE_BODY, headers={"content-type": "text/event-stream"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = OpenAICompatibleProvider(
            OpenAICompatibleConfig(
                api_key="test-key",
                base_url="https://example.test/v1",
                max_retries=1,
                max_retry_delay_seconds=0,
            ),
            client=client,
        )
        first_events = [
            event
            async for event in provider.stream_response(
                model="test-model",
                system="",
                messages=[UserMessage(content="Hi")],
                tools=[],
            )
        ]
        done = first_events[-1]
        assert isinstance(done, AssistantDoneEvent)
        assert any(item.type == "provider_retry" for item in done.message.diagnostics or [])
        # Diagnostics are session metadata: provider_context() keeps them on the
        # message, but a follow-up request must not serialize them as model input.
        _ = [
            event
            async for event in provider.stream_response(
                model="test-model",
                system="",
                messages=[UserMessage(content="Hi"), done.message, UserMessage(content="Continue")],
                tools=[],
            )
        ]

    assert len(requests) == 3
    body = requests[2].content.decode()
    assert "provider_retry" not in body
    assert "rate limited" not in body


def test_default_retry_delay_cap_fits_a_real_retry_after() -> None:
    assert DEFAULT_OPENAI_COMPATIBLE_MAX_RETRY_DELAY_SECONDS == 15.0


def test_env_parsing_uses_the_raised_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_MAX_RETRY_DELAY_SECONDS", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    config = openai_compatible_config_from_env()

    assert config.max_retry_delay_seconds == 15.0


def test_env_override_still_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MAX_RETRY_DELAY_SECONDS", "2.5")

    config = openai_compatible_config_from_env()

    assert config.max_retry_delay_seconds == 2.5
