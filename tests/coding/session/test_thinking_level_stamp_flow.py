"""End-to-end check: a thinking-level change reaches the next response.

The funnel test (tests/ai/test_thinking_level_stamping.py) pins the
adapter-level stamp; this pins the coding-layer half of the chain:
``set_thinking_level`` rebuilds the runtime provider unconditionally
(``model_runtime.refresh_runtime_provider``), so the next assistant message
is stamped with the NEW requested level and the request payload carries the
fresh reasoning effort. If a provider cache ever appears in front of the
refresh, this test is the tripwire.
"""

from __future__ import annotations

from json import loads
from pathlib import Path

import httpx
import pytest

import baldric.ai.openai_compatible as openai_compatible_module
from baldric.agent import AssistantMessage, MessageEndEvent, UserMessage
from baldric.ai import FakeProvider
from baldric.coding import (
    BaldricPaths,
    BaldricResourcePaths,
    CodingSession,
    CodingSessionConfig,
    OpenAICompatibleProviderConfig,
    ProviderSettings,
)
from baldric.coding.session import JsonlSessionStorage
from baldric.protocol.session import MessageEntry

_MODEL = "test-reasoner"

_SSE = 'data: {"choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'


@pytest.mark.anyio
async def test_set_thinking_level_stamps_the_next_response(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, text=_SSE, headers={"content-type": "text/event-stream"})

    def fake_create_async_client(**kwargs: object) -> httpx.AsyncClient:
        del kwargs
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # Only the socket is faked: the real provider factory, the real
    # level-to-effort mapping, and the real stamping funnel all run.
    monkeypatch.setattr(openai_compatible_module, "create_async_client", fake_create_async_client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    provider_config = OpenAICompatibleProviderConfig(
        name="stamp-test",
        models=(_MODEL,),
        default_model=_MODEL,
        thinking_levels=("off", "medium", "high"),
        # Without a declared wire parameter the provider has no effort to
        # record, so the stamp is None by design (selection.py guards this).
        thinking_parameter="reasoning_effort",
    )
    storage = JsonlSessionStorage(tmp_path / "session.jsonl")
    await storage.append(MessageEntry(message=UserMessage(content="hello")))
    session = await CodingSession.load(
        CodingSessionConfig(
            # Placeholder instance; the runtime provider is built from the
            # provider settings below, like every coding session.
            provider=FakeProvider([]),
            model=_MODEL,
            system="You are Baldric.",
            storage=storage,
            cwd=tmp_path,
            provider_name="stamp-test",
            provider_settings=ProviderSettings(providers=(provider_config,)),
            runtime_provider_config=provider_config,
            resource_paths=BaldricResourcePaths(
                root=tmp_path / ".baldric",
                paths=BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"),
            ),
        )
    )

    def stamped_level(events: list[object]) -> str | None:
        message = next(
            event.message
            for event in events
            if isinstance(event, MessageEndEvent) and isinstance(event.message, AssistantMessage)
        )
        return message.thinking_level

    def prompt_payload(text: str) -> dict[str, object]:
        """The captured request whose user turn is exactly ``text``.

        Session housekeeping requests (e.g. transcript naming) also hit the
        provider, with thinking deliberately stripped and a different system
        prompt, so requests are matched by system prompt plus exact user turn.
        """
        return next(
            loads(request.content)
            for request in requests
            if loads(request.content)["messages"][0]["content"] == "You are Baldric."
            and any(
                isinstance(block, dict) and block.get("content") == text
                for block in loads(request.content)["messages"]
            )
        )

    events = [event async for event in session.prompt("first")]
    assert session.thinking_level == "medium"
    assert stamped_level(events) == "medium"
    first_payload = prompt_payload("first")
    assert first_payload.get("reasoning_effort") == "medium", first_payload

    await session.set_thinking_level("high")
    events = [event async for event in session.prompt("second")]
    assert stamped_level(events) == "high"
    assert prompt_payload("second")["reasoning_effort"] == "high"

    # The off level rides the same chain through the none->off inversion; the
    # wire omits the key unless the provider declares an off->none metadata
    # mapping (both spellings mean off).
    await session.set_thinking_level("off")
    events = [event async for event in session.prompt("third")]
    assert stamped_level(events) == "off"
    assert prompt_payload("third").get("reasoning_effort") in (None, "none")
