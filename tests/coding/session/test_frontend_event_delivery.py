"""Session-level events reach a frontend, not only extensions.

`SessionInfoChangedEvent` and `ThinkingLevelChangedEvent` are published to
extensions the moment they happen, but a frontend only consumes the `prompt()`
stream - so a handler for them could never fire. Queue them and hand them to the
next stream, before the run's own events.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from baldric_agent.messages import AssistantMessage
from baldric_agent.session import InMemorySessionStorage
from baldric_ai import FakeProvider
from baldric_coding.config.paths import BaldricPaths
from baldric_coding.events import SessionInfoChangedEvent, ThinkingLevelChangedEvent
from baldric_coding.session.manager import SessionManager
from baldric_coding.session.session import CodingSession, CodingSessionConfig
from tests.helpers.pi_event_helpers import assistant_done, assistant_start


async def _session(tmp_path: Path) -> CodingSession:
    manager = SessionManager(BaldricPaths(home=tmp_path / ".baldric", agents_home=tmp_path / ".agents"))
    record = manager.create_session(cwd=tmp_path, model="fake", provider_name="fake")
    return await CodingSession.load(
        CodingSessionConfig(
            provider=FakeProvider(
                [
                    [assistant_start(), assistant_done(AssistantMessage(content="ok"))],
                    [assistant_start(), assistant_done(AssistantMessage(content="ok"))],
                ]
            ),
            model="fake",
            system="You are Baldric.",
            storage=InMemorySessionStorage(),
            cwd=tmp_path,
            provider_name="fake",
            session_id=record.id,
            session_manager=manager,
            extensions_enabled=False,
        )
    )


@pytest.mark.anyio
async def test_a_queued_session_event_leads_the_stream(tmp_path: Path) -> None:
    session = await _session(tmp_path)
    try:
        session.queue_frontend_event(SessionInfoChangedEvent(name="renamed"))

        events = [event async for event in session.prompt("go")]

        assert isinstance(events[0], SessionInfoChangedEvent)
        assert events[0].name == "renamed"
        assert events[1].type == "agent_start"
    finally:
        await session.aclose()


@pytest.mark.anyio
async def test_a_queued_event_is_delivered_once(tmp_path: Path) -> None:
    session = await _session(tmp_path)
    try:
        session.queue_frontend_event(ThinkingLevelChangedEvent(level="high"))

        first = [event async for event in session.prompt("go")]
        second = [event async for event in session.prompt("go")]

        assert sum(isinstance(event, ThinkingLevelChangedEvent) for event in first) == 1
        assert not any(isinstance(event, ThinkingLevelChangedEvent) for event in second)
    finally:
        await session.aclose()


@pytest.mark.anyio
async def test_renaming_a_session_queues_the_frontend_event(tmp_path: Path) -> None:
    session = await _session(tmp_path)
    try:
        await session.set_session_name("audit-followups")

        events = [event async for event in session.prompt("go")]

        info_events = [event for event in events if isinstance(event, SessionInfoChangedEvent)]
        assert info_events and info_events[0].name == "audit-followups"
    finally:
        await session.aclose()


@pytest.mark.anyio
async def test_an_empty_queue_changes_nothing(tmp_path: Path) -> None:
    session = await _session(tmp_path)
    try:
        events = [event async for event in session.prompt("go")]

        assert events[0].type == "agent_start"
    finally:
        await session.aclose()
