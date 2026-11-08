"""Harness run lifecycle.

`prompt()` used to arm the cancel token lazily, inside an async generator body
that does not run until the first `__anext__`. Two user-visible consequences
followed: `cancel()` right after `prompt()` did nothing, and a run that was
created but never iterated left `_running` true forever, so every later
`prompt()` raised "already running". These tests pin the fixed lifecycle.
"""

from __future__ import annotations

import gc

import pytest

from baldric_agent import AgentHarness, AgentHarnessConfig, AssistantMessage, UserMessage
from baldric_ai import FakeProvider
from tests.helpers.pi_event_helpers import assistant_done, assistant_start


def _harness() -> AgentHarness:
    provider = FakeProvider([[assistant_start(), assistant_done(AssistantMessage(content="Hello"))]])
    return AgentHarness(AgentHarnessConfig(provider=provider, model="fake", system="You are Baldric."))


def _assistant_messages(harness: AgentHarness) -> list[AssistantMessage]:
    return [message for message in harness.messages if isinstance(message, AssistantMessage)]


@pytest.mark.anyio
async def test_cancel_before_the_first_event_still_cancels() -> None:
    harness = _harness()
    run = harness.prompt("do the work")

    # No event has been pulled yet; the run must already be armed.
    harness.cancel()

    events = [event async for event in run]

    assert events, "the run must still report its start and its aborted turn"
    assert _assistant_messages(harness)[-1].stop_reason == "aborted"
    assert not harness.is_running


@pytest.mark.anyio
async def test_dropping_a_run_before_iterating_releases_the_harness() -> None:
    harness = _harness()
    run = harness.prompt("first")
    assert harness.is_running

    del run
    gc.collect()

    assert not harness.is_running
    events = [event async for event in harness.prompt("second")]
    assert events
    assert _assistant_messages(harness)[-1].stop_reason == "stop"


@pytest.mark.anyio
async def test_aclose_releases_the_harness_and_is_idempotent() -> None:
    harness = _harness()
    run = harness.prompt("first")
    await run.aclose()
    await run.aclose()

    assert not harness.is_running


@pytest.mark.anyio
async def test_overlap_is_rejected_until_the_open_run_is_closed() -> None:
    harness = _harness()
    run = harness.prompt("first")

    with pytest.raises(RuntimeError, match="already running"):
        harness.prompt("second")

    await run.aclose()
    events = [event async for event in harness.prompt("second")]
    assert events


@pytest.mark.anyio
async def test_completing_a_run_releases_the_harness() -> None:
    harness = _harness()
    events = [event async for event in harness.prompt("hello")]

    assert events
    assert not harness.is_running
    assert harness.continue_ is not None  # a further run must be possible


@pytest.mark.anyio
async def test_continue_also_arms_its_cancel_token_immediately() -> None:
    """Behavior change (pi parity): the tail must be continuable at all.

    The old test continued from an assistant tail and expected an aborted
    turn; continue_ now rejects that up front (pi agent.ts:403-417), so the
    arming property is pinned with a continuable transcript instead.
    """
    harness = _harness()
    harness.append_message(UserMessage(content="previous"))
    run = harness.continue_()

    harness.cancel()

    events = [event async for event in run]
    assert events
    assert _assistant_messages(harness)[-1].stop_reason == "aborted"
    assert not harness.is_running


@pytest.mark.anyio
async def test_continue_rejects_an_empty_transcript() -> None:
    harness = _harness()

    with pytest.raises(RuntimeError, match="No messages to continue from"):
        harness.continue_()


@pytest.mark.anyio
async def test_continue_from_assistant_tail_without_queue_continues_the_context() -> None:
    """Deliberate divergence from pi (agent.ts:416): assistant tails continue.

    The prelude repair guarantees no unanswered tool call reaches the
    provider, and the coding layer's failover retry continues after a failed
    turn; pi rejects the tail because it has no equivalent repair-or-failover
    path.
    """
    harness = _harness()
    harness.append_message(AssistantMessage(content="previous", stop_reason="stop"))

    events = [event async for event in harness.continue_()]

    assert events
    assert events[-1].type == "agent_end"
    assert not harness.is_running


@pytest.mark.anyio
async def test_continue_from_assistant_tail_drains_queued_steering_as_prompt() -> None:
    """Pi agent.ts:403-408: queued steering satisfies the continuation."""
    provider = FakeProvider([[assistant_start(), assistant_done(AssistantMessage(content="Hello"))]])
    harness = AgentHarness(AgentHarnessConfig(provider=provider, model="fake", system="You are Baldric."))
    harness.append_message(AssistantMessage(content="previous", stop_reason="stop"))
    harness.steer_message(UserMessage(content="queued"))

    _ = [event async for event in harness.continue_()]

    assert provider.calls[0][2][-1].text == "queued"
    assert harness.pending_message_count == 0
    assert not harness.is_running
