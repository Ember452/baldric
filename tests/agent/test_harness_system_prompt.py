"""``update_system_prompt`` replaces the prompt read by subsequent runs."""

from __future__ import annotations

import pytest

from baldric.agent import AgentHarness, AgentHarnessConfig, AssistantMessage
from baldric.ai import FakeProvider
from tests.helpers.pi_event_helpers import assistant_done, assistant_start

pytestmark = pytest.mark.anyio


def anyio_backend() -> str:
    return "asyncio"


async def _run(harness: AgentHarness, text: str) -> None:
    _ = [event async for event in harness.prompt(text)]


async def test_run_after_update_sends_new_system_prompt() -> None:
    assistant = AssistantMessage(content="Hello")
    provider = FakeProvider(
        [
            [assistant_start(), assistant_done(assistant)],
            [assistant_start(), assistant_done(assistant)],
        ]
    )
    harness = AgentHarness(AgentHarnessConfig(provider=provider, model="fake", system="OLD"))

    await _run(harness, "Hi")
    harness.update_system_prompt("NEW")
    await _run(harness, "Again")

    assert provider.calls[0][1] == "OLD"
    assert provider.calls[1][1] == "NEW"


async def test_update_rejects_empty_prompt() -> None:
    harness = AgentHarness(AgentHarnessConfig(provider=FakeProvider([]), model="fake", system="OLD"))

    with pytest.raises(ValueError, match="non-empty"):
        harness.update_system_prompt("")
